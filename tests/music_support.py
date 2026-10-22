"""Fakes shared by the music tests: a silent backend and tiny wav files."""
import os
import wave


def make_wav(path, seconds=1.0):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(8000 * seconds))
    return str(path)


class FakeBackend:
    """Same methods as MciBackend; time only passes when the test says so."""

    def __init__(self, alias=""):
        self.alias = alias
        self.loaded = None
        self.playing = False
        self.position = 0
        self.length = 5000
        self.volume = 80
        self.fail_for = set()
        self.ended = False

    def load(self, path):
        if os.path.basename(path) in self.fail_for:
            return False
        self.loaded, self.position, self.ended, self.playing = path, 0, False, False
        return True

    def play(self):
        self.playing = True

    def pause(self):
        self.playing = False

    def resume(self):
        self.playing = True

    def stop(self):
        self.playing, self.position = False, 0

    def close(self):
        self.loaded, self.playing = None, False

    def position_ms(self):
        return self.position

    def is_playing(self):
        return self.playing and not self.ended

    def length_ms(self):
        return self.length

    def seek(self, ms):
        self.position = ms

    def set_volume(self, percent):
        self.volume = percent

    def finished(self):
        return self.ended




class FakeEqBackend(FakeBackend):
    """The equalizer's backend (sdl_player) in the tests: remembers the filter it was given."""

    def __init__(self, alias=""):
        super().__init__(alias)
        self.filter = ""

    def set_filter(self, text):
        self.filter = text

class FakeReader:
    """Same interface as app.tags.TagReader, answered by the test instead of ffprobe."""

    def __init__(self, *a, **k):
        self.tag_requests, self.cover_requests = [], []
        self.pending = []                       # answers the window will get on its next look
        self.stopped = False

    def request(self, path):
        self.tag_requests.append(path)

    def request_cover(self, path):
        self.cover_requests.append(path)

    def answer_tags(self, path, **info):
        self.pending.append(("tags", path, info))

    def answer_cover(self, path, jpg):
        self.pending.append(("cover", path, jpg))

    def drain(self):
        out, self.pending = self.pending, []
        return out

    def stop(self):
        self.stopped = True

    def save(self):
        pass


class FakeKeys:
    """Same interface as app.mediakeys.MediaKeys, without taking the real keyboard keys."""

    def __init__(self):
        import queue
        self.pressed = queue.Queue()
        self.active = False
        self.starts = 0
        self.extra = {}

    def set_extra(self, keys):
        self.extra = {name: combo for name, combo in (keys or {}).items() if combo}

    def start(self):
        self.active = True
        self.starts += 1
        return {"toggle", "next", "previous", "stop"}

    def stop(self):
        self.active = False


class FakeSearcher:
    """Same interface as app.music_search.Searcher; the test gives the answer."""

    def __init__(self, *a, **k):
        self.asked = []
        self.answer = None
        self.busy = False
        self.query = ""

    def search(self, query, *more):
        self.asked.append(query)
        self.more = more
        self.query = query
        self.busy = True

    def run(self, query, work):
        """📻 and the like: the work is done at once (it is given fakes by the test)."""
        self.asked.append(query)
        self.query = query
        self.busy = True
        self.answer = (query, work(), "")

    def give(self, results, error="", query=None):
        self.answer = (query or (self.asked[-1] if self.asked else ""), results, error)

    def poll(self):
        answer, self.answer = self.answer, None
        if answer:
            self.busy = False
        return answer


class FakeOverlay:
    """Same interface as app.smtc.MediaOverlay; remembers what it was told."""

    def __init__(self):
        import queue
        self.pressed = queue.Queue()
        self.shown = []
        self.states = []
        self.closed = False

    def show(self, title, artist="", album="", cover=None):
        if not self.shown or self.shown[-1] != (title, artist, album, cover):
            self.shown.append((title, artist, album, cover))

    def status(self, state):
        if not self.states or self.states[-1] != state:
            self.states.append(state)

    def close(self):
        self.closed = True


class FakeThumbBar:
    """Same interface as app.taskbar.ThumbBar, without the real taskbar."""

    def __init__(self):
        import queue
        self.pressed = queue.Queue()
        self.active = False
        self.playing = False
        self.attached_to = None

    def attach(self, hwnd, folder):
        self.active, self.attached_to = True, hwnd
        return True

    def set_playing(self, playing):
        self.playing = playing

    def detach(self):
        self.active = False
