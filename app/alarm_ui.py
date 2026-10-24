"""⏰ The music alarm's window: on / off, the time, the days, the list, how slowly the volume rises."""
import customtkinter as ctk

from . import alarm
from .ui_common import fit_geometry, set_if_changed, set_window_icon

HOURS = [f"{h:02d}" for h in range(24)]
MINUTES = [f"{m:02d}" for m in range(0, 60, 5)]


class AlarmWindow(ctk.CTkToplevel):
    def __init__(self, music):
        super().__init__(music)
        set_window_icon(self)
        self.music = music
        self.title("DISO • Müzikli alarm")
        fit_geometry(self, 460, 520)
        self.resizable(False, False)
        self.columnconfigure(0, weight=1)
        self.setting = alarm.clean(music.store.state.get("alarm"))
        ctk.CTkLabel(self, text="⏰ Müzikli alarm", font=ctk.CTkFont(size=22, weight="bold"), anchor="w").grid(
            row=0, column=0, sticky="ew", padx=20, pady=(16, 2))
        ctk.CTkLabel(self, text="Seçtiğin saatte bir liste başlar, sesi yavaşça açılır. DISO açık olmalı (tepside "
                                "de olur) ve bilgisayar uykuda olmamalı.", text_color="gray", anchor="w",
                     justify="left", wraplength=410).grid(row=1, column=0, sticky="ew", padx=20)
        box = ctk.CTkFrame(self)
        box.grid(row=2, column=0, sticky="ew", padx=16, pady=12)
        box.columnconfigure(1, weight=1)

        self.on = ctk.CTkSwitch(box, text="Alarm açık", command=self._changed)
        self.on.select() if self.setting["on"] else self.on.deselect()
        self.on.grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 6))

        ctk.CTkLabel(box, text="Saat").grid(row=1, column=0, sticky="w", padx=14, pady=6)
        clock = ctk.CTkFrame(box, fg_color="transparent")
        clock.grid(row=1, column=1, sticky="w", pady=6)
        h, m = alarm.parse_time(self.setting["time"])
        self.hour = ctk.CTkOptionMenu(clock, values=HOURS, width=70, command=lambda v: self._changed())
        self.hour.set(f"{h:02d}")
        self.hour.pack(side="left")
        ctk.CTkLabel(clock, text=":", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left", padx=4)
        minutes = MINUTES if f"{m:02d}" in MINUTES else sorted(set(MINUTES + [f"{m:02d}"]))
        self.minute = ctk.CTkOptionMenu(clock, values=minutes, width=70, command=lambda v: self._changed())
        self.minute.set(f"{m:02d}")
        self.minute.pack(side="left")

        ctk.CTkLabel(box, text="Günler").grid(row=2, column=0, sticky="nw", padx=14, pady=6)
        days = ctk.CTkFrame(box, fg_color="transparent")
        days.grid(row=2, column=1, sticky="w", pady=6)
        self.days = []
        for i, name in enumerate(alarm.DAYS):
            cb = ctk.CTkCheckBox(days, text=name, width=56, checkbox_width=18, checkbox_height=18, command=self._changed)
            cb.select() if i in self.setting["days"] else cb.deselect()
            cb.grid(row=i // 4, column=i % 4, sticky="w", pady=2)
            self.days.append(cb)

        ctk.CTkLabel(box, text="Liste").grid(row=3, column=0, sticky="w", padx=14, pady=6)
        names = music.store.names()
        self.list_menu = ctk.CTkOptionMenu(box, values=names, width=220, command=lambda v: self._changed())
        self.list_menu.set(self.setting["list"] if self.setting["list"] in names else music.viewed)
        self.list_menu.grid(row=3, column=1, sticky="w", pady=6)

        ctk.CTkLabel(box, text="Ses açılsın").grid(row=4, column=0, sticky="w", padx=14, pady=6)
        self.fade = ctk.CTkOptionMenu(box, values=list(alarm.FADES), width=150, command=lambda v: self._changed())
        self.fade.set(next((k for k, v in alarm.FADES.items() if v == self.setting["fade"]), "1 dakikada"))
        self.fade.grid(row=4, column=1, sticky="w", pady=6)

        self.shuffle = ctk.CTkCheckBox(box, text="Karışık çal", command=self._changed)
        self.shuffle.select() if self.setting["shuffle"] else self.shuffle.deselect()
        self.shuffle.grid(row=5, column=1, sticky="w", pady=(6, 12))

        self.next_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=14, weight="bold"))
        self.next_label.grid(row=3, column=0, pady=(0, 6))
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=4, column=0, pady=(4, 16))
        ctk.CTkButton(foot, text="▶ Şimdi dene", width=120, fg_color="transparent", border_width=1,
                      text_color=("gray20", "gray85"), command=self.try_now).pack(side="left", padx=6)
        ctk.CTkButton(foot, text="Kapat", width=90, command=self.destroy).pack(side="left", padx=6)
        self.bind("<Escape>", lambda e: self.destroy())
        self._show_next()

    def read(self) -> dict:
        return alarm.clean({"on": bool(self.on.get()), "time": f"{self.hour.get()}:{self.minute.get()}",
                            "days": [i for i, cb in enumerate(self.days) if cb.get()], "list": self.list_menu.get(),
                            "fade": alarm.FADES.get(self.fade.get(), 60), "shuffle": bool(self.shuffle.get()),
                            "last": self.setting.get("last", "")})

    def _changed(self):
        new = self.read()
        if (new["time"], new["days"]) != (self.setting["time"], self.setting["days"]):
            new["last"] = ""                                 # a new time today rings today
        self.setting = new
        self.music.store.set_state(alarm=new)
        self._show_next()

    def _show_next(self):
        at = alarm.next_ring(self.setting)
        set_if_changed(self.next_label, text=f"Sonraki alarm: {alarm.when_text(at)}" if at else
                       ("Alarm kapalı" if not self.setting["on"] else "Bir gün seç"))

    def try_now(self):
        """Ring at once (with the fade), to hear how it will be."""
        self.music.ring_alarm(dict(self.setting, on=True))
