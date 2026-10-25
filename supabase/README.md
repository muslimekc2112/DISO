# DISO's online part: Supabase

The account, the sync between computers, friends, chats and groups live in a free [Supabase](https://supabase.com)
project. DISO needs no server of its own: the database (with *row level security*) says who may see what.

**Setup (once)**

1. Make a project (Free plan, Frankfurt). Take its *Project URL* and its *publishable* key (Project Settings →
   API Keys) and put them in `app/account.py` (`SUPABASE`, `API_KEY`). Never the *secret* / `service_role` key.
2. SQL Editor → New query → paste all of [`schema.sql`](schema.sql) → Run. It is safe to run again (after an
   update of this file, run it again).
3. Authentication → Sign In / Providers → Email: on, *Confirm email* on.
4. Authentication → Emails → Templates: in *Confirm signup* and *Reset Password* the mail shows the code
   `{{ .Token }}` (not the link): e.g. `<p style="font-size:32px;letter-spacing:6px">{{ .Token }}</p>`.
5. Authentication → Emails → SMTP Settings: your own SMTP (Gmail with an app password works) — Supabase's own
   sender sends only a few mails an hour.

**What is where**

| | |
|---|---|
| `profiles` | user name, name, last seen, the song playing now, status (never the e-mail) |
| `user_files`, `devices` | the synced files, the computers of an account |
| `shared_lists` | playlists sent with a code (`get_shared(code)` gives one list for one exact code) |
| `friend_requests`, `friendships`, `blocks` | friends (`accept_request`, `unfriend`, `block_user`) |
| `conversations`, `members`, `messages`, `reactions` | chats of two and groups (the same tables); `create_group`, `group_*` |
| `notifications` | likes, answers, "deleted the account" |
| storage bucket `files` | what is sent in chats (50 MB each; only the members of the chat read it) |

Realtime (the live connection) is on for the tables that tell DISO to look. The tests (`tests/fake_supabase.py`)
use a pretend Supabase that keeps the same rules.
