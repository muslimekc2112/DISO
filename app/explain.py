"""❓ "Neden inmedi?": a download's technical error in plain words, with the one click that fixes it when
there is one. explain(error) -> (reason, fix): fix is one of FIXES (or None when nothing can be done)."""

# (words to look for, the reason, the fix) — the first rule that matches wins
RULES = [
    (("private video", "this video is private", "video is private"),
     "Video gizli: sahibi izin vermedikçe indirilemiyor.", None),
    (("video unavailable", "has been removed", "no longer available", "this video has been deleted",
      "account associated with this video has been terminated"),
     "Video kaldırılmış ya da artık yok.", None),
    (("drm", "widevine"), "İçerik kopya korumalı (DRM): indirilemiyor.", None),
    (("confirm your age", "age-restricted", "age restricted", "inappropriate for some users"),
     "Yaş sınırlı video: site giriş yapmanı istiyor.", "cookies"),
    (("sign in to confirm", "not a bot", "login required", "members-only", "join this channel",
      "requires authentication", "use --cookies", "cookies"),
     "Site giriş yapmanı istiyor.", "cookies"),
    (("not available in your country", "geo restrict", "geo-restrict", "blocked it in your country",
      "not made this video available in your country"),
     "Bu içerik ülkende engelli.", "proxy"),
    (("no space left", "errno 28", "disk full", "not enough space", "yeterli alan"),
     "Diskte yer kalmadı.", "folder"),
    (("permission denied", "errno 13", "access is denied", "erişim engellendi", "winerror 5"),
     "İndirme klasörüne yazma izni yok.", "folder"),
    (("ffmpeg", "ffprobe"), "Video / ses birleştirme aracı (FFmpeg) eksik ya da bozuk.", "tools"),
    (("unable to extract", "nsig", "signature extraction", "failed to extract", "please report this issue",
      "player response", "requested format is not available"),
     "Site değişmiş: indirme aracının yeni sürümü gerekiyor.", "tools"),
    (("http error 404", "404 not found", "404: not found"),
     "Dosya sunucuda yok: link bozuk ya da kaldırılmış.", None),
    (("http error 403", "403 forbidden", "forbidden"),
     "Sunucu izin vermedi (link süresi dolmuş olabilir).", "retry"),
    (("http error 429", "too many requests"),
     "Site çok fazla istek aldı, biraz bekletiyor.", "retry"),
    (("timed out", "timeout", "connection reset", "connection aborted", "remote end closed", "max retries",
      "temporary failure in name resolution", "getaddrinfo", "network is unreachable", "connection refused",
      "bağlantı", "incomplete read", "ssl"),
     "İnternet bağlantısı koptu ya da sunucu cevap vermedi.", "retry"),
    (("unsupported url",), "Bu linkte indirilebilecek bir video ya da dosya bulamadım.", None),
]

FIXES = {
    "cookies": "Giriş çerezlerini aç ve tekrar dene",
    "retry": "Kaldığı yerden tekrar dene",
    "folder": "Başka bir klasör seç ve tekrar dene",
    "proxy": "Proxy ayarını aç",
    "tools": "İndirme araçlarını güncelle",
}
UNKNOWN = "Beklenmedik bir hata oldu."


def explain(error):
    """(plain reason, fix key or None)."""
    low = (error or "").lower()
    for words, reason, fix in RULES:
        if any(w in low for w in words):
            return reason, fix
    return UNKNOWN, "retry"


def cookie_browser(found, names):
    """The browser whose sign-ins to use: Firefox first (its cookies can always be read), then Edge, then
    Chrome — among the ones on this PC (found: extension_setup ids) and the names DISO offers."""
    for bid, name in (("firefox", "Firefox"), ("edge", "Edge"), ("chrome", "Chrome"), ("brave", "Brave"),
                      ("opera", "Opera"), ("vivaldi", "Vivaldi")):
        if bid in found:
            match = next((n for n in names if n.lower() == name.lower()), None)
            if match:
                return match
    return None
