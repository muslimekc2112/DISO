"""A pretend Supabase for the tests: its Authentication (sign up with a mailed code, sign in, refresh, recovery), its
database (tables, filters, upserts, functions) with the same row level security as supabase/schema.sql, and its file
storage. app.account._call is put here (see the fixtures of the test files), so no test needs the internet.

Whoever calls is told by the access token in the headers (anon: no token). A refused request raises the same
AccountError the real answer would."""
import re
import uuid

from app import account

REQUEST_KEYS = {"select", "order", "limit", "offset", "on_conflict", "columns"}
UNIQUE = {"profiles": [("id",), ("username",)], "user_files": [("user_id", "name")],
          "devices": [("user_id", "device_id")], "shared_lists": [("code",)], "blocks": [("user_id", "blocked_id")],
          "friendships": [("user_id", "friend_id")], "friend_requests": [("from_id", "to_id")],
          "conversations": [("id",), ("direct_key",)], "members": [("conversation_id", "user_id")],
          "messages": [("id",)], "reactions": [("message_id", "user_id")], "notifications": [("id",)]}
TABLES = list(UNIQUE)


class FakeSupabase:
    def __init__(self):
        self.users = {}            # e-mail -> {"id", "password", "confirmed", "code", "recovery", "meta"}
        self.tokens = {}           # access token -> user id
        self.refresh = {}          # refresh token -> user id
        self.t = {name: [] for name in TABLES}
        self.files = {}            # storage path -> bytes
        self.mails = []            # (kind, e-mail, code)
        self.offline = False
        self.disabled_signup = False
        self.counter = 0

    # ------------------------------------------------------------------ small helpers
    @staticmethod
    def _refuse(body, status=400):
        raise account.AccountError(*account._message(body, status))

    def _new(self, prefix):
        self.counter += 1
        return f"{prefix}{self.counter}"

    def _uid(self, headers):
        auth = (headers or {}).get("Authorization", "")
        return self.tokens.get(auth[len("Bearer "):]) if auth.startswith("Bearer ") else None

    def user(self, address):
        return self.users[address]

    def last_code(self, address):
        return next(code for kind, a, code in reversed(self.mails) if a == address)

    def uid_of(self, username):
        return next(r["id"] for r in self.t["profiles"] if r["username"] == username)

    def _session(self, user):
        access, refresh = self._new("tok-"), self._new("ref-")
        self.tokens[access], self.refresh[refresh] = user["id"], user["id"]
        return {"access_token": access, "refresh_token": refresh, "expires_in": 3600,
                "user": {"id": user["id"], "email": next(a for a, u in self.users.items() if u is user)}}

    def expire(self, uid):
        """Every access token of this user is old now (the refresh token still works)."""
        for tok in [k for k, v in self.tokens.items() if v == uid]:
            del self.tokens[tok]

    # ------------------------------------------------------------------ the one door
    def __call__(self, method, url, timeout=None, json=None, headers=None, params=None, data=None, **kw):
        if self.offline:
            raise account.AccountError("İnternete ulaşamadım. Bağlantını kontrol edip tekrar dene.", "OFFLINE")
        assert (headers or {}).get("apikey") == account.API_KEY, "no key"
        if url.startswith(account.AUTH_URL):
            return self._auth(method, url[len(account.AUTH_URL) + 1:], json, headers, params)
        if url.startswith(account.REST_URL):
            return self._rest(method, url[len(account.REST_URL) + 1:], json, headers, dict(params or {}))
        if url.startswith(account.STORAGE_URL):
            return self._storage(method, url[len(account.STORAGE_URL) + 1:], json, headers, data)
        raise AssertionError(url)

    # ------------------------------------------------------------------ Authentication
    def _auth(self, method, path, body, headers, params):
        body = body or {}
        if path == "signup":
            if self.disabled_signup:
                self._refuse({"error_code": "signup_disabled", "msg": "no"}, 422)
            address, meta = body["email"], body.get("data") or {}
            if len(body.get("password", "")) < 6:
                self._refuse({"error_code": "weak_password", "msg": "weak"}, 422)
            if address in self.users and self.users[address]["confirmed"]:
                return {"id": "x", "email": address, "identities": []}          # (no hint that it exists)
            if address not in self.users:
                uid = str(uuid.uuid4())
                if any(r["username"] == meta.get("username") for r in self.t["profiles"]):
                    self._refuse({"error_code": "unexpected_failure", "msg": "Database error saving new user"}, 500)
                self.users[address] = {"id": uid, "password": body["password"], "confirmed": False, "code": "",
                                       "recovery": "", "meta": meta}
                self.t["profiles"].append({"id": uid, "username": meta.get("username"),
                                           "first_name": meta.get("first_name", ""), "last_name": meta.get("last_name", ""),
                                           "photo": None, "status": "online", "seen": None, "now_playing": "",
                                           "created_at": account.iso()})
            self._mail("signup", address)
            return {"id": self.users[address]["id"], "email": address, "identities": [{"provider": "email"}]}
        if path == "resend":
            if body["email"] in self.users and not self.users[body["email"]]["confirmed"]:
                self._mail("signup", body["email"])
            return {}
        if path == "verify":
            user = self.users.get(body["email"])
            key = "recovery" if body.get("type") == "recovery" else "code"
            if user is None or not user[key] or user[key] != body.get("token"):
                self._refuse({"error_code": "otp_expired", "msg": "Token has expired or is invalid"}, 403)
            user[key] = ""
            user["confirmed"] = True
            return self._session(user)
        if path == "token":
            if (params or {}).get("grant_type") == "refresh_token":
                uid = self.refresh.pop(body.get("refresh_token"), None)
                if uid is None:
                    self._refuse({"error_code": "refresh_token_not_found", "msg": "x"}, 400)
                return self._session(next(u for u in self.users.values() if u["id"] == uid))
            user = self.users.get(body.get("email"))
            if user is None or user["password"] != body.get("password"):
                self._refuse({"error": "invalid_grant", "error_description": "Invalid login credentials"}, 400)
            if not user["confirmed"]:
                self._refuse({"error_code": "email_not_confirmed", "msg": "Email not confirmed"}, 400)
            return self._session(user)
        if path == "recover":
            if body["email"] in self.users:
                self.users[body["email"]]["recovery"] = self._mail("recovery", body["email"])
            return {}
        if path == "user" and method == "PUT":
            uid = self._uid(headers)
            if uid is None:
                self._refuse({}, 401)
            user = next(u for u in self.users.values() if u["id"] == uid)
            if len(body.get("password", "")) < 6:
                self._refuse({"error_code": "weak_password", "msg": "weak"}, 422)
            user["password"] = body["password"]
            return {"id": uid}
        raise AssertionError(path)

    def _mail(self, kind, address):
        code = f"{len(self.mails) + 100001:06d}"
        self.mails.append((kind, address, code))
        if kind == "signup":
            self.users[address]["code"] = code
        return code

    # ------------------------------------------------------------------ the database: rows and rules
    def _member(self, conv, uid):
        return any(m["conversation_id"] == conv and m["user_id"] == uid for m in self.t["members"])

    def _admin(self, conv, uid):
        return any(m["conversation_id"] == conv and m["user_id"] == uid and m["role"] == "admin"
                   for m in self.t["members"])

    def _friends(self, a, b):
        return any(f["user_id"] == a and f["friend_id"] == b for f in self.t["friendships"])

    def _blocked(self, a, b):
        return any((x["user_id"], x["blocked_id"]) in ((a, b), (b, a)) for x in self.t["blocks"])

    def _conv_of_message(self, mid):
        return next((m["conversation_id"] for m in self.t["messages"] if m["id"] == mid), None)

    def _allowed(self, table, op, row, uid, new=None):
        if uid is None:
            return False
        if table == "profiles":
            return op == "select" or (op == "update" and row["id"] == uid and new["id"] == uid)
        if table in ("user_files", "devices", "blocks"):
            return row["user_id"] == uid and (new is None or new["user_id"] == uid)
        if table == "shared_lists":
            return row["owner"] == uid and (new is None or new["owner"] == uid)
        if table == "friendships":
            return op == "select" and uid in (row["user_id"], row["friend_id"])
        if table == "friend_requests":
            if op == "select":
                return uid in (row["from_id"], row["to_id"])
            if op == "insert":
                return (row["from_id"] == uid and not self._blocked(uid, row["to_id"])
                        and not self._friends(uid, row["to_id"]))
            return op == "delete" and uid in (row["from_id"], row["to_id"])
        if table == "conversations":
            if op == "select":
                return self._member(row["id"], uid)
            return op == "update" and row["kind"] == "group" and self._admin(row["id"], uid) and new["kind"] == "group"
        if table == "members":
            if op == "select":
                return self._member(row["conversation_id"], uid)
            return op == "update" and row["user_id"] == uid and new["user_id"] == uid
        if table == "messages":
            if op == "select":
                return self._member(row["conversation_id"], uid)
            if op == "insert":
                conv = next(c for c in self.t["conversations"] if c["id"] == row["conversation_id"]) \
                    if any(c["id"] == row["conversation_id"] for c in self.t["conversations"]) else None
                if conv is None or row["sender_id"] != uid or row["kind"] == "system" or not self._member(conv["id"], uid):
                    return False
                if conv["only_admins"] and not self._admin(conv["id"], uid):
                    return False
                if conv["kind"] == "direct":
                    return any(m["user_id"] != uid and self._friends(uid, m["user_id"])
                               for m in self.t["members"] if m["conversation_id"] == conv["id"])
                return True
            return op == "update" and row["sender_id"] == uid and new["sender_id"] == uid
        if table == "reactions":
            conv = self._conv_of_message(row["message_id"])
            if conv is None or not self._member(conv, uid):
                return False
            return op == "select" or (row["user_id"] == uid and (new is None or new["user_id"] == uid))
        if table == "notifications":
            if op == "insert":
                return row["from_id"] == uid and self._friends(uid, row["user_id"])
            return row["user_id"] == uid and (new is None or new["user_id"] == uid)
        raise AssertionError(table)

    @staticmethod
    def _cmp(value, arg):
        if isinstance(value, bool):
            return value == (arg == "true")
        if isinstance(value, (int, float)):
            try:
                return float(value) == float(arg)
            except ValueError:
                return False
        return ("" if value is None else str(value)) == arg

    def _matches(self, row, filters):
        for key, expr in filters.items():
            op, _, arg = expr.partition(".")
            value = row.get(key)
            if op == "eq":
                ok = self._cmp(value, arg)
            elif op == "neq":
                ok = not self._cmp(value, arg)
            elif op in ("gt", "gte", "lt", "lte"):
                a, b = (float(value or 0), float(arg)) if isinstance(value, (int, float)) and not isinstance(value, bool) \
                    else (str(value or ""), arg)
                ok = {"gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b}[op]
            elif op == "in":
                ok = any(self._cmp(value, x.strip('"')) for x in arg.strip("()").split(","))
            elif op == "ilike":
                ok = bool(re.fullmatch(re.escape(arg).replace("\\*", ".*"), str(value or ""), re.I))
            elif op == "is":
                ok = (value is None) == (arg == "null")
            else:
                raise AssertionError(expr)
            if not ok:
                return False
        return True

    def _defaults(self, table, row, uid):
        row = dict(row)
        now = account.iso()
        if table in ("user_files", "devices", "blocks"):
            row.setdefault("user_id", uid)
        if table == "user_files":
            row.setdefault("device", "")
            row.setdefault("version", "")
        if table == "devices":
            row.setdefault("name", "")
            row.setdefault("seen", now)
            row.setdefault("version", "")
            row.setdefault("signed_out", False)
        if table == "shared_lists":
            row.setdefault("owner", uid)
            row.setdefault("by_name", "")
            row.setdefault("made", now)
        if table == "friend_requests":
            row.setdefault("from_id", uid)
            row.setdefault("at", now)
        if table == "conversations":
            row.setdefault("id", str(uuid.uuid4()))
            for k, v in (("name", ""), ("about", ""), ("emoji", "👥"), ("photo", None), ("only_admins", False),
                         ("direct_key", None), ("created_by", uid), ("created_at", now)):
                row.setdefault(k, v)
        if table == "members":
            for k, v in (("role", "member"), ("joined_at", now), ("last_read", now), ("muted", False)):
                row.setdefault(k, v)
        if table == "messages":
            row.setdefault("id", self.counter_id())
            for k, v in (("sender_id", uid), ("kind", "text"), ("body", ""), ("payload", None), ("reply_to", None),
                         ("deleted", False), ("created_at", now)):
                row.setdefault(k, v)
        if table == "reactions":
            row.setdefault("user_id", uid)
        if table == "notifications":
            row.setdefault("id", self.counter_id())
            for k, v in (("from_id", uid), ("body", ""), ("payload", None), ("seen", False), ("created_at", now)):
                row.setdefault(k, v)
        return row

    def counter_id(self):
        self.counter += 1
        return self.counter

    def _dup(self, table, row, skip=None):
        for cols in UNIQUE[table]:
            if cols == ("direct_key",) and row.get("direct_key") is None:
                continue
            for other in self.t[table]:
                if other is not skip and all(other.get(c) == row.get(c) for c in cols):
                    return cols
        return None

    def _rest(self, method, path, body, headers, params):
        uid = self._uid(headers)
        if headers.get("Authorization") and uid is None:
            self._refuse({"code": "PGRST303", "message": "JWT expired"}, 401)
        if path.startswith("rpc/"):
            return self._rpc(path[4:], body or {}, uid)
        table = path
        assert table in self.t, table
        prefer = headers.get("Prefer", "")
        filters = {k: v for k, v in params.items() if k not in REQUEST_KEYS}
        if method == "GET":
            rows = [r for r in self.t[table] if self._matches(r, filters) and self._allowed(table, "select", r, uid)]
            if params.get("order"):
                col, _, way = params["order"].partition(".")
                rows.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=way == "desc")
            rows = rows[:int(params["limit"])] if params.get("limit") else rows
            return [dict(r) for r in rows]
        if method == "POST":
            made = []
            for raw in (body if isinstance(body, list) else [body]):
                row = self._defaults(table, raw, uid)
                clash = self._dup(table, row)
                if clash and "merge-duplicates" in prefer:
                    existing = next(r for r in self.t[table] if all(r.get(c) == row.get(c) for c in clash))
                    new = {**existing, **raw}
                    if not self._allowed(table, "update", existing, uid, new):
                        self._refuse({"code": "42501", "message": "new row violates row-level security policy"}, 403)
                    existing.update(new)
                    made.append(dict(existing))
                    continue
                if clash:
                    self._refuse({"code": "23505", "message": "duplicate key value"}, 409)
                if not self._allowed(table, "insert", row, uid):
                    self._refuse({"code": "42501", "message": "new row violates row-level security policy"}, 403)
                self.t[table].append(row)
                made.append(dict(row))
            return made if "return=representation" in prefer else {}
        if method in ("PATCH", "DELETE"):
            hit = [r for r in self.t[table] if self._matches(r, filters) and self._allowed(table, "select", r, uid)] \
                if table not in ("devices", "user_files", "blocks", "friend_requests", "reactions", "notifications") \
                else [r for r in self.t[table] if self._matches(r, filters)]
            for r in hit:
                if method == "DELETE":
                    if self._allowed(table, "delete", r, uid):
                        self.t[table].remove(r)
                    continue
                new = {**r, **body}
                if self._allowed(table, "update", r, uid, new):
                    r.update(new)
            return {}
        raise AssertionError(method)

    # ------------------------------------------------------------------ the functions
    def _rpc(self, name, a, uid):
        if name == "username_free":
            return not any(r["username"] == a["name"].lower() for r in self.t["profiles"])
        if name == "get_shared":
            return [{"name": r["name"], "by_name": r["by_name"], "songs": r["songs"], "made": r["made"]}
                    for r in self.t["shared_lists"] if r["code"] == a["list_code"].upper()]
        if uid is None:
            self._refuse({"code": "42501", "message": f"permission denied for function {name}"}, 401)
        method = getattr(self, "fn_" + name, None)
        assert method is not None, name
        return method(uid, **a)

    def fn_accept_request(self, uid, from_user):
        if not any(r["from_id"] == from_user and r["to_id"] == uid for r in self.t["friend_requests"]):
            self._refuse({"code": "P0001", "message": "NO_REQUEST"}, 400)
        self.t["friend_requests"] = [r for r in self.t["friend_requests"]
                                     if (r["from_id"], r["to_id"]) not in ((from_user, uid), (uid, from_user))]
        for a, b in ((uid, from_user), (from_user, uid)):
            if not self._friends(a, b):
                self.t["friendships"].append({"user_id": a, "friend_id": b, "since": account.iso()})
        return {}

    def fn_unfriend(self, uid, other):
        self.t["friendships"] = [f for f in self.t["friendships"] if (f["user_id"], f["friend_id"]) not in
                                 ((uid, other), (other, uid))]
        return {}

    def fn_block_user(self, uid, other):
        if not any(b["user_id"] == uid and b["blocked_id"] == other for b in self.t["blocks"]):
            self.t["blocks"].append({"user_id": uid, "blocked_id": other})
        self.fn_unfriend(uid, other)
        self.t["friend_requests"] = [r for r in self.t["friend_requests"] if (r["from_id"], r["to_id"]) not in
                                     ((uid, other), (other, uid))]
        return {}

    def fn_unblock_user(self, uid, other):
        self.t["blocks"] = [b for b in self.t["blocks"] if not (b["user_id"] == uid and b["blocked_id"] == other)]
        return {}

    def fn_direct_chat(self, uid, other):
        if not self._friends(uid, other):
            self._refuse({"code": "P0001", "message": "NOT_FRIENDS"}, 400)
        key = ":".join(sorted((uid, other)))
        found = next((c for c in self.t["conversations"] if c["direct_key"] == key), None)
        if found is None:
            found = self._defaults("conversations", {"kind": "direct", "direct_key": key}, uid)
            self.t["conversations"].append(found)
            for u in (uid, other):
                self.t["members"].append(self._defaults("members", {"conversation_id": found["id"], "user_id": u}, uid))
        return found["id"]

    def _say(self, conv, text, uid=None):
        self.t["messages"].append(self._defaults("messages", {"conversation_id": conv, "sender_id": uid,
                                                              "kind": "system", "body": text}, uid))

    def fn_create_group(self, uid, group_name, group_about, group_emoji, people):
        if not group_name.strip():
            self._refuse({"code": "P0001", "message": "NO_NAME"}, 400)
        if len(people or []) > 49:
            self._refuse({"code": "P0001", "message": "TOO_MANY"}, 400)
        conv = self._defaults("conversations", {"kind": "group", "name": group_name.strip(),
                                                "about": group_about or "", "emoji": group_emoji or "👥"}, uid)
        self.t["conversations"].append(conv)
        self.t["members"].append(self._defaults("members", {"conversation_id": conv["id"], "user_id": uid,
                                                            "role": "admin"}, uid))
        for p in people or []:
            if self._friends(uid, p) and not self._blocked(uid, p):
                self.t["members"].append(self._defaults("members", {"conversation_id": conv["id"], "user_id": p}, uid))
        self._say(conv["id"], "created", uid)
        return conv["id"]

    def _need_admin(self, uid, conv):
        if not self._admin(conv, uid):
            self._refuse({"code": "P0001", "message": "NOT_ADMIN"}, 400)

    def fn_group_add(self, uid, conv, person):
        self._need_admin(uid, conv)
        if not self._friends(uid, person):
            self._refuse({"code": "P0001", "message": "NOT_FRIENDS"}, 400)
        if sum(1 for m in self.t["members"] if m["conversation_id"] == conv) >= 50:
            self._refuse({"code": "P0001", "message": "TOO_MANY"}, 400)
        if not self._member(conv, person):
            self.t["members"].append(self._defaults("members", {"conversation_id": conv, "user_id": person}, uid))
        self._say(conv, f"added:{person}", uid)
        return {}

    def fn_group_remove(self, uid, conv, person):
        self._need_admin(uid, conv)
        self.t["members"] = [m for m in self.t["members"] if not (m["conversation_id"] == conv and m["user_id"] == person)]
        self._say(conv, f"removed:{person}", uid)
        return {}

    def fn_group_role(self, uid, conv, person, new_role):
        self._need_admin(uid, conv)
        for m in self.t["members"]:
            if m["conversation_id"] == conv and m["user_id"] == person:
                m["role"] = new_role
        self._say(conv, f"{new_role}:{person}", uid)
        return {}

    def fn_group_leave(self, uid, conv):
        self.t["members"] = [m for m in self.t["members"] if not (m["conversation_id"] == conv and m["user_id"] == uid)]
        rest = [m for m in self.t["members"] if m["conversation_id"] == conv]
        if not rest:
            self.t["conversations"] = [c for c in self.t["conversations"] if c["id"] != conv]
            self.t["messages"] = [m for m in self.t["messages"] if m["conversation_id"] != conv]
            return {}
        if not any(m["role"] == "admin" for m in rest):
            min(rest, key=lambda m: m["joined_at"])["role"] = "admin"
        self._say(conv, "left", uid)
        return {}

    def fn_group_delete(self, uid, conv):
        self._need_admin(uid, conv)
        self.t["conversations"] = [c for c in self.t["conversations"] if c["id"] != conv]
        for t in ("members", "messages"):
            self.t[t] = [r for r in self.t[t] if r["conversation_id"] != conv]
        return {}

    def fn_unread_counts(self, uid):
        out = []
        for m in self.t["members"]:
            if m["user_id"] != uid:
                continue
            n = sum(1 for g in self.t["messages"] if g["conversation_id"] == m["conversation_id"]
                    and g["created_at"] > m["last_read"] and g["sender_id"] != uid and not g["deleted"]
                    and g["kind"] != "system")
            if n:
                out.append({"conversation_id": m["conversation_id"], "n": n})
        return out

    def fn_delete_me(self, uid):
        address = next(a for a, u in self.users.items() if u["id"] == uid)
        del self.users[address]
        self.tokens = {k: v for k, v in self.tokens.items() if v != uid}
        for table in self.t:
            keep = []
            for r in self.t[table]:
                if table == "messages" and r["sender_id"] == uid:
                    r["sender_id"] = None
                if table == "notifications" and r["from_id"] == uid:
                    r["from_id"] = None
                if table == "conversations" and r["created_by"] == uid:
                    r["created_by"] = None
                gone = ((table == "profiles" and r["id"] == uid) or r.get("user_id") == uid or r.get("owner") == uid
                        or r.get("from_id") == uid and table == "friend_requests"
                        or r.get("to_id") == uid or r.get("friend_id") == uid or r.get("blocked_id") == uid)
                if not gone:
                    keep.append(r)
            self.t[table] = keep
        return {}

    # ------------------------------------------------------------------ file storage
    def _storage(self, method, path, body, headers, data):
        """/object/list/<bucket> (POST), /object/<bucket>/<key> (POST upload), /object/authenticated/<bucket>/<key>
        (GET), /object/<bucket> (DELETE with {"prefixes": [...]}) like the real storage."""
        uid = self._uid(headers)
        if uid is None:
            self._refuse({"statusCode": "403", "message": "Unauthorized"}, 403)
        parts = path.split("/")
        assert parts[0] == "object", path
        if parts[1] == "list":
            prefix = (body or {}).get("prefix", "")
            if not self._member(prefix, uid):
                return []
            return [{"name": p[len(prefix) + 1:]} for p in self.files if p.startswith(prefix + "/")]
        if parts[1] == "authenticated":
            key = "/".join(parts[3:])
        elif len(parts) == 2 and method == "DELETE":
            for key in (body or {}).get("prefixes", []):
                if self._member(key.split("/", 1)[0], uid):
                    self.files.pop(key, None)
            return {}
        else:
            key = "/".join(parts[2:])
        if not self._member(key.split("/", 1)[0], uid):
            self._refuse({"statusCode": "403", "message": "new row violates row-level security policy"}, 403)
        if method == "POST":
            self.files[key] = data if isinstance(data, bytes) else bytes(data.read())
            return {"Key": key}
        return self.files[key]

    def raw(self, method, url, **kw):
        """The same door, for what is not JSON."""
        out = self(method, url, **kw)
        return out if isinstance(out, bytes) else b""
