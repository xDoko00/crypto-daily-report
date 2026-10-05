# -*- coding: utf-8 -*-
"""Kayıtlı bir günün raporunu e-posta bültenine (Buttondown) elle gönderir.

    python bulten_gonder.py [YYYY-MM-DD] [--taslak]

Tarih verilmezse bugün (TSİ). Rapor üretmez, Telegram'a göndermez, commit
atmaz; yalnız reports/YYYY/MM/<tarih>.json → eposta.gonder. Başarısızsa
çıkış kodu 1 (.github/workflows/bulten.yml).
"""
import json
import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import eposta

KOK = os.path.dirname(os.path.abspath(__file__))


def rapor_yolu(tarih, kok=KOK):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", tarih or ""):
        raise ValueError(f"tarih YYYY-MM-DD olmalı: {tarih!r}")
    return os.path.join(kok, "reports", tarih[:4], tarih[5:7], f"{tarih}.json")


def bugun_tsi():
    return datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%Y-%m-%d")


def main(argv=None, gonder=None, kok=KOK):
    argv = sys.argv[1:] if argv is None else argv
    taslak = "--taslak" in argv
    tarihler = [a for a in argv if not a.startswith("--") and a.strip()]
    tarih = tarihler[0].strip() if tarihler else bugun_tsi()
    try:
        yol = rapor_yolu(tarih, kok)
        with open(yol, encoding="utf-8") as f:
            rapor = json.load(f)
    except (ValueError, OSError, json.JSONDecodeError) as e:
        print(f"[HATA] Rapor okunamadı: {e}", file=sys.stderr)
        return 1
    ok, mesaj = (gonder or eposta.gonder)(rapor, taslak=taslak)
    print(f"[{'başarılı' if ok else 'HATA'}] {tarih}: {mesaj}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
