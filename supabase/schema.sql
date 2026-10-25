-- DISO on Supabase: every table, its security (row level security: each person sees only what is theirs or
-- shared with them) and the functions that do what a single row rule cannot (making friends on both sides,
-- managing a group). Paste all of it into Supabase → SQL Editor → New query → Run. Running it again is safe.

create extension if not exists pgcrypto;

-- (an older version had helpers that took any two people: they go, with the rules built on them; all of it is
-- made again below)
drop function if exists public.blocked(uuid, uuid) cascade;
drop function if exists public.friends_with(uuid, uuid) cascade;

-- ============================================================================ profiles (what others may see)
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  username text unique not null check (username ~ '^[a-z0-9._]{3,20}$'),
  first_name text not null default '',
  last_name text not null default '',
  photo text check (photo is null or length(photo) <= 200000),       -- a small picture (data URL)
  status text not null default 'online' check (status in ('online', 'busy', 'invisible')),
  seen timestamptz,
  now_playing text not null default '',
  created_at timestamptz not null default now()
);
alter table public.profiles enable row level security;
drop policy if exists "profiles: read when signed in" on public.profiles;
create policy "profiles: read when signed in" on public.profiles for select to authenticated using (true);
drop policy if exists "profiles: own row" on public.profiles;
create policy "profiles: own row" on public.profiles for update to authenticated
  using (id = auth.uid()) with check (id = auth.uid());

-- a new account gets its profile from what was given at sign-up (the e-mail never goes there)
create or replace function public.on_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, username, first_name, last_name)
  values (new.id, lower(new.raw_user_meta_data ->> 'username'),
          coalesce(new.raw_user_meta_data ->> 'first_name', ''), coalesce(new.raw_user_meta_data ->> 'last_name', ''));
  return new;
end $$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users for each row execute function public.on_new_user();

-- is a user name still free? (asked before signing up, so anyone may ask)
create or replace function public.username_free(name text) returns boolean
language sql stable security definer set search_path = public as $$
  select not exists (select 1 from public.profiles where username = lower(name));
$$;
grant execute on function public.username_free(text) to anon, authenticated;

-- ============================================================================ synced files, computers
create table if not exists public.user_files (
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  name text not null,
  data text not null,
  updated double precision not null,
  device text not null default '',
  version text not null default '',
  primary key (user_id, name)
);
alter table public.user_files enable row level security;
drop policy if exists "user_files: own" on public.user_files;
create policy "user_files: own" on public.user_files for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());

create table if not exists public.devices (
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  device_id text not null,
  name text not null default '',
  seen timestamptz not null default now(),
  version text not null default '',
  signed_out boolean not null default false,
  primary key (user_id, device_id)
);
alter table public.devices enable row level security;
drop policy if exists "devices: own" on public.devices;
create policy "devices: own" on public.devices for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());

-- ============================================================================ playlists shared with a code
create table if not exists public.shared_lists (
  code text primary key check (code ~ '^[A-Z2-9]{8}$'),
  owner uuid not null default auth.uid() references auth.users(id) on delete cascade,
  name text not null,
  by_name text not null default '',
  songs jsonb not null,
  made timestamptz not null default now()
);
alter table public.shared_lists enable row level security;
drop policy if exists "shared_lists: own" on public.shared_lists;
create policy "shared_lists: own" on public.shared_lists for all to authenticated
  using (owner = auth.uid()) with check (owner = auth.uid());

-- one list by its code (nobody can list them all), for anyone who has the code
create or replace function public.get_shared(list_code text)
returns table (name text, by_name text, songs jsonb, made timestamptz)
language sql stable security definer set search_path = public as $$
  select name, by_name, songs, made from public.shared_lists where code = upper(list_code);
$$;
grant execute on function public.get_shared(text) to anon, authenticated;

-- ============================================================================ blocking, friends
create table if not exists public.blocks (
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  blocked_id uuid not null references auth.users(id) on delete cascade,
  primary key (user_id, blocked_id)
);
alter table public.blocks enable row level security;
drop policy if exists "blocks: own" on public.blocks;
create policy "blocks: own" on public.blocks for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());

-- did I block them, or they me? (only about oneself: nobody can ask about two other people)
create or replace function public.blocked_with(other uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.blocks
                  where (user_id = auth.uid() and blocked_id = other) or (user_id = other and blocked_id = auth.uid()));
$$;

create table if not exists public.friendships (
  user_id uuid not null references auth.users(id) on delete cascade,
  friend_id uuid not null references auth.users(id) on delete cascade,
  since timestamptz not null default now(),
  primary key (user_id, friend_id)
);
alter table public.friendships enable row level security;
drop policy if exists "friendships: see own" on public.friendships;
create policy "friendships: see own" on public.friendships for select to authenticated
  using (auth.uid() in (user_id, friend_id));

-- are we friends? (only about oneself)
create or replace function public.friend_of(other uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.friendships where user_id = auth.uid() and friend_id = other);
$$;

create table if not exists public.friend_requests (
  from_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  to_id uuid not null references auth.users(id) on delete cascade,
  at timestamptz not null default now(),
  primary key (from_id, to_id),
  check (from_id <> to_id)
);
alter table public.friend_requests enable row level security;
drop policy if exists "requests: see own" on public.friend_requests;
create policy "requests: see own" on public.friend_requests for select to authenticated
  using (auth.uid() in (from_id, to_id));
drop policy if exists "requests: send" on public.friend_requests;
create policy "requests: send" on public.friend_requests for insert to authenticated
  with check (from_id = auth.uid() and not public.blocked_with(to_id) and not public.friend_of(to_id));
drop policy if exists "requests: take back or say no" on public.friend_requests;
create policy "requests: take back or say no" on public.friend_requests for delete to authenticated
  using (auth.uid() in (from_id, to_id));

-- yes to a request: friends on both sides at once (also when both asked)
create or replace function public.accept_request(from_user uuid) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not exists (select 1 from public.friend_requests where from_id = from_user and to_id = auth.uid()) then
    raise exception 'NO_REQUEST';
  end if;
  delete from public.friend_requests
   where (from_id = from_user and to_id = auth.uid()) or (from_id = auth.uid() and to_id = from_user);
  insert into public.friendships (user_id, friend_id) values (auth.uid(), from_user), (from_user, auth.uid())
    on conflict do nothing;
end $$;
grant execute on function public.accept_request(uuid) to authenticated;

create or replace function public.unfriend(other uuid) returns void
language sql security definer set search_path = public as $$
  delete from public.friendships
   where (user_id = auth.uid() and friend_id = other) or (user_id = other and friend_id = auth.uid());
$$;
grant execute on function public.unfriend(uuid) to authenticated;

-- ============================================================================ chats and groups
create table if not exists public.conversations (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('direct', 'group')),
  name text not null default '' check (length(name) <= 60),
  about text not null default '' check (length(about) <= 300),
  emoji text not null default '👥',
  photo text check (photo is null or length(photo) <= 200000),
  only_admins boolean not null default false,           -- 📢 only the admins write (an announcements group)
  direct_key text unique,                                -- the two people of a direct chat, in order
  created_by uuid default auth.uid() references auth.users(id) on delete set null,
  created_at timestamptz not null default now()
);
create table if not exists public.members (
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null default 'member' check (role in ('admin', 'member')),
  joined_at timestamptz not null default now(),
  last_read timestamptz not null default now(),
  muted boolean not null default false,
  primary key (conversation_id, user_id)
);
create table if not exists public.messages (
  id bigint generated always as identity primary key,
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  sender_id uuid default auth.uid() references auth.users(id) on delete set null,
  kind text not null default 'text' check (kind in ('text', 'song', 'playlist', 'image', 'file', 'system')),
  body text not null default '' check (length(body) <= 4000),
  payload jsonb,
  reply_to bigint references public.messages(id) on delete set null,
  deleted boolean not null default false,
  created_at timestamptz not null default now()
);
create index if not exists messages_by_chat on public.messages (conversation_id, created_at);
create table if not exists public.reactions (
  message_id bigint not null references public.messages(id) on delete cascade,
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  emoji text not null check (length(emoji) <= 16),
  primary key (message_id, user_id)
);

create or replace function public.is_member(conv uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.members where conversation_id = conv and user_id = auth.uid());
$$;
create or replace function public.is_admin(conv uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.members where conversation_id = conv and user_id = auth.uid() and role = 'admin');
$$;

alter table public.conversations enable row level security;
drop policy if exists "conversations: members see" on public.conversations;
create policy "conversations: members see" on public.conversations for select to authenticated
  using (public.is_member(id));
drop policy if exists "conversations: admins change" on public.conversations;
create policy "conversations: admins change" on public.conversations for update to authenticated
  using (kind = 'group' and public.is_admin(id)) with check (kind = 'group' and public.is_admin(id));

alter table public.members enable row level security;
drop policy if exists "members: members see" on public.members;
create policy "members: members see" on public.members for select to authenticated
  using (public.is_member(conversation_id));
drop policy if exists "members: own read mark and mute" on public.members;
create policy "members: own read mark and mute" on public.members for update to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());

alter table public.messages enable row level security;
drop policy if exists "messages: members read" on public.messages;
create policy "messages: members read" on public.messages for select to authenticated
  using (public.is_member(conversation_id));
drop policy if exists "messages: members write" on public.messages;
create policy "messages: members write" on public.messages for insert to authenticated
  with check (sender_id = auth.uid() and kind <> 'system' and public.is_member(conversation_id)
              and (public.is_admin(conversation_id)
                   or not (select only_admins from public.conversations c where c.id = conversation_id)));
drop policy if exists "messages: own delete" on public.messages;
create policy "messages: own delete" on public.messages for update to authenticated
  using (sender_id = auth.uid()) with check (sender_id = auth.uid());

alter table public.reactions enable row level security;
drop policy if exists "reactions: members" on public.reactions;
create policy "reactions: members" on public.reactions for select to authenticated
  using (public.is_member((select conversation_id from public.messages m where m.id = message_id)));
drop policy if exists "reactions: own" on public.reactions;
create policy "reactions: own" on public.reactions for insert to authenticated
  with check (user_id = auth.uid() and public.is_member((select conversation_id from public.messages m where m.id = message_id)));
drop policy if exists "reactions: own change" on public.reactions;
create policy "reactions: own change" on public.reactions for update to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists "reactions: own remove" on public.reactions;
create policy "reactions: own remove" on public.reactions for delete to authenticated using (user_id = auth.uid());

create or replace function public.say(conv uuid, text_ text) returns void
language sql security definer set search_path = public as $$
  insert into public.messages (conversation_id, sender_id, kind, body) values (conv, auth.uid(), 'system', text_);
$$;

-- the chat with a friend (made the first time)
create or replace function public.direct_chat(other uuid) returns uuid
language plpgsql security definer set search_path = public as $$
declare key text; conv uuid;
begin
  if not public.friend_of(other) then raise exception 'NOT_FRIENDS'; end if;
  key := least(auth.uid()::text, other::text) || ':' || greatest(auth.uid()::text, other::text);
  select id into conv from public.conversations where direct_key = key;
  if conv is null then
    insert into public.conversations (kind, direct_key) values ('direct', key) returning id into conv;
    insert into public.members (conversation_id, user_id) values (conv, auth.uid()), (conv, other);
  end if;
  return conv;
end $$;
grant execute on function public.direct_chat(uuid) to authenticated;

-- a group: whoever makes it is its admin; friends of theirs join it at once (as in WhatsApp)
create or replace function public.create_group(group_name text, group_about text, group_emoji text, people uuid[])
returns uuid language plpgsql security definer set search_path = public as $$
declare conv uuid; p uuid;
begin
  if length(trim(group_name)) = 0 then raise exception 'NO_NAME'; end if;
  if coalesce(array_length(people, 1), 0) > 49 then raise exception 'TOO_MANY'; end if;
  insert into public.conversations (kind, name, about, emoji) values ('group', trim(group_name), coalesce(group_about, ''),
    coalesce(nullif(group_emoji, ''), '👥')) returning id into conv;
  insert into public.members (conversation_id, user_id, role) values (conv, auth.uid(), 'admin');
  foreach p in array coalesce(people, '{}') loop
    if public.friend_of(p) and not public.blocked_with(p) then
      insert into public.members (conversation_id, user_id) values (conv, p) on conflict do nothing;
    end if;
  end loop;
  perform public.say(conv, 'created');
  return conv;
end $$;
grant execute on function public.create_group(text, text, text, uuid[]) to authenticated;

create or replace function public.group_add(conv uuid, person uuid) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not public.is_admin(conv) then raise exception 'NOT_ADMIN'; end if;
  if not public.friend_of(person) then raise exception 'NOT_FRIENDS'; end if;
  if (select count(*) from public.members where conversation_id = conv) >= 50 then raise exception 'TOO_MANY'; end if;
  insert into public.members (conversation_id, user_id) values (conv, person) on conflict do nothing;
  perform public.say(conv, 'added:' || person);
end $$;
grant execute on function public.group_add(uuid, uuid) to authenticated;

create or replace function public.group_remove(conv uuid, person uuid) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not public.is_admin(conv) or person = auth.uid() then raise exception 'NOT_ADMIN'; end if;
  delete from public.members where conversation_id = conv and user_id = person;
  perform public.say(conv, 'removed:' || person);
end $$;
grant execute on function public.group_remove(uuid, uuid) to authenticated;

create or replace function public.group_role(conv uuid, person uuid, new_role text) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not public.is_admin(conv) then raise exception 'NOT_ADMIN'; end if;
  update public.members set role = new_role where conversation_id = conv and user_id = person;
  perform public.say(conv, new_role || ':' || person);
end $$;
grant execute on function public.group_role(uuid, uuid, text) to authenticated;

-- leaving: the last admin hands the group to the oldest member; the last one out deletes it
create or replace function public.group_leave(conv uuid) returns void
language plpgsql security definer set search_path = public as $$
declare heir uuid;
begin
  delete from public.members where conversation_id = conv and user_id = auth.uid();
  if not exists (select 1 from public.members where conversation_id = conv) then
    delete from public.conversations where id = conv;
    return;
  end if;
  if not exists (select 1 from public.members where conversation_id = conv and role = 'admin') then
    select user_id into heir from public.members where conversation_id = conv order by joined_at limit 1;
    update public.members set role = 'admin' where conversation_id = conv and user_id = heir;
  end if;
  perform public.say(conv, 'left');
end $$;
grant execute on function public.group_leave(uuid) to authenticated;

create or replace function public.group_delete(conv uuid) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not public.is_admin(conv) then raise exception 'NOT_ADMIN'; end if;
  delete from public.conversations where id = conv and kind = 'group';
end $$;
grant execute on function public.group_delete(uuid) to authenticated;

-- ============================================================================ notifications (likes, answers)
create table if not exists public.notifications (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users(id) on delete cascade,          -- who gets it
  from_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  kind text not null check (kind in ('like', 'feedback')),
  body text not null default '' check (length(body) <= 500),
  payload jsonb,
  seen boolean not null default false,
  created_at timestamptz not null default now()
);
alter table public.notifications enable row level security;
drop policy if exists "notifications: own" on public.notifications;
create policy "notifications: own" on public.notifications for select to authenticated using (user_id = auth.uid());
drop policy if exists "notifications: own seen" on public.notifications;
create policy "notifications: own seen" on public.notifications for update to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists "notifications: own remove" on public.notifications;
create policy "notifications: own remove" on public.notifications for delete to authenticated using (user_id = auth.uid());
drop policy if exists "notifications: friends send" on public.notifications;
create policy "notifications: friends send" on public.notifications for insert to authenticated
  with check (from_id = auth.uid() and public.friend_of(user_id));

-- ============================================================================ files sent in chats
insert into storage.buckets (id, name, public, file_size_limit)
values ('files', 'files', false, 52428800) on conflict (id) do nothing;
drop policy if exists "files: members upload" on storage.objects;
create policy "files: members upload" on storage.objects for insert to authenticated
  with check (bucket_id = 'files' and public.is_member(((storage.foldername(name))[1])::uuid));
drop policy if exists "files: members read" on storage.objects;
create policy "files: members read" on storage.objects for select to authenticated
  using (bucket_id = 'files' and public.is_member(((storage.foldername(name))[1])::uuid));
drop policy if exists "files: own remove" on storage.objects;
create policy "files: own remove" on storage.objects for delete to authenticated
  using (bucket_id = 'files' and owner = auth.uid());

-- ============================================================================ deleting the account
-- (the files the account sent are deleted by DISO through the Storage API first: Supabase does not let SQL do it)
create or replace function public.delete_me() returns void
language plpgsql security definer set search_path = public as $$
begin
  delete from auth.users where id = auth.uid();            -- everything above goes with it (on delete cascade)
end $$;
grant execute on function public.delete_me() to authenticated;

-- ============================================================================ live (Realtime)
do $$
declare t text;
begin
  foreach t in array array['messages', 'members', 'conversations', 'friend_requests', 'friendships', 'notifications',
                            'reactions'] loop
    if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and tablename = t) then
      execute format('alter publication supabase_realtime add table public.%I', t);
    end if;
  end loop;
end $$;

-- ============================================================================ version 2: counts, blocking, notifications
-- notifications outlive the account of whoever sent them ("X deleted the account" is one of them)
alter table public.notifications alter column from_id drop not null;
do $$
declare c text;
begin                                                       -- (whatever the old foreign key on from_id is called)
  for c in select conname from pg_constraint
            where conrelid = 'public.notifications'::regclass and contype = 'f'
              and conkey = array[(select attnum from pg_attribute
                                   where attrelid = 'public.notifications'::regclass and attname = 'from_id')]
  loop
    execute format('alter table public.notifications drop constraint %I', c);
  end loop;
end $$;
alter table public.notifications add constraint notifications_from_id_fkey
  foreign key (from_id) references auth.users(id) on delete set null;
alter table public.notifications drop constraint if exists notifications_kind_check;
alter table public.notifications add constraint notifications_kind_check check (kind in ('like', 'feedback', 'gone'));

-- messages from others that I have not read, for each of my chats
create or replace function public.unread_counts() returns table (conversation_id uuid, n bigint)
language sql stable security definer set search_path = public as $$
  select m.conversation_id, count(*) from public.members m
    join public.messages g on g.conversation_id = m.conversation_id
   where m.user_id = auth.uid() and g.created_at > m.last_read and g.sender_id is distinct from auth.uid()
     and not g.deleted and g.kind <> 'system'
   group by m.conversation_id;
$$;

-- blocking: no more requests, they are no longer friends, no messages in a chat of two
create or replace function public.block_user(other uuid) returns void
language plpgsql security definer set search_path = public as $$
begin
  insert into public.blocks (user_id, blocked_id) values (auth.uid(), other) on conflict do nothing;
  delete from public.friendships
   where (user_id = auth.uid() and friend_id = other) or (user_id = other and friend_id = auth.uid());
  delete from public.friend_requests
   where (from_id = auth.uid() and to_id = other) or (from_id = other and to_id = auth.uid());
end $$;

create or replace function public.unblock_user(other uuid) returns void
language sql security definer set search_path = public as $$
  delete from public.blocks where user_id = auth.uid() and blocked_id = other;
$$;

-- the chat of two is closed once they are not friends any more (or one blocked the other)
drop policy if exists "messages: members write" on public.messages;
create policy "messages: members write" on public.messages for insert to authenticated
  with check (
    sender_id = auth.uid() and kind <> 'system' and public.is_member(conversation_id)
    and (public.is_admin(conversation_id)
         or not (select only_admins from public.conversations c where c.id = conversation_id))
    and (not exists (select 1 from public.conversations c where c.id = conversation_id and c.kind = 'direct')
         or exists (select 1 from public.members o
                     where o.conversation_id = messages.conversation_id and o.user_id <> auth.uid()
                       and public.friend_of(o.user_id))));

-- ============================================================================ who may call which function
-- (Supabase lets everyone call every function by default: only these two are for anyone, the rest only for
-- signed-in people; the helpers inside the rules answer only about the one who asks)
revoke execute on all functions in schema public from public, anon;
grant execute on function public.username_free(text) to anon, authenticated;
grant execute on function public.get_shared(text) to anon, authenticated;
grant execute on all functions in schema public to authenticated;
revoke execute on function public.on_new_user() from authenticated;
revoke execute on function public.say(uuid, text) from authenticated;
