# -*- coding: utf-8 -*-
"""
Günlük raporun KANONİK veri sözleşmesi.
=======================================

Rapor artık tek bir yerde üretilir: bu modüldeki şemaya uyan bir JSON.
Telegram mesajı, web sitesi sayfası, paylaşım kartı ve sesli özet — hepsi
o JSON'dan türetilir. Böylece dört kanal arasında tutarsızlık olamaz.

İş bölümü nettir ve bilerek katıdır:
  * SAYISAL PİYASA VERİSİ  → yalnızca CoinGecko/Alternative.me'den, Python
    tarafından doldurulur. LLM bu alanlara hiç dokunmaz (uydurma riski sıfır).
  * METİN/ANALİZ           → LLM üretir, ama her gündem maddesi kaynak URL'i
    zorunludur; şema kaynaksız maddeyi geçirmez.

Kullanım:
    rapor = sema.rapor_kur(market=..., llm_ciktisi=..., tarih_id=...)
    sema.dogrula(rapor)          # hata varsa RaporSemaHatasi fırlatır
"""

import json
import os
import re
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

SEMA_SURUMU = 1

VARSAYILAN_YAZAR = {
    "name": "Doğukan Doğan",
    "url": "https://dogukanlive.com/hakkimda",
}

UYARI_METNI = "Bilgilendirme amaçlıdır, yatırım tavsiyesi değildir."

# Brief'teki "Hava" alanının kabul edilen değerleri (prompt da bunları dayatır).
HAVA_DEGERLERI = ["Temkinli", "İyimser", "Kararsız", "Riskli"]

# Gündem maddesi önem dereceleri → Telegram/web'de renk simgesine dönüşür.
ONEM_DEGERLERI = ["kritik", "onemli", "bilgi"]


class RaporSemaHatasi(ValueError):
    """Rapor şemaya uymuyor. Mesaj Türkçe ve hangi alanın bozuk olduğunu söyler."""


# --------------------------------------------------------------------------- #
# Şema parçaları
# --------------------------------------------------------------------------- #

_SAYI_YA_DA_BOS = {"type": ["number", "null"]}
_TAMSAYI_YA_DA_BOS = {"type": ["integer", "null"]}

_KAYNAK = {
    "type": "object",
    "required": ["url", "title"],
    "additionalProperties": False,
    "properties": {
        # Yalnızca https: web backend'i bu URL'leri yeniden yayınlayacağı için
        # http/javascript/data şemalarına kapı açmıyoruz.
        "url": {"type": "string", "pattern": r"^https://[^\s]+$", "maxLength": 500},
        "title": {"type": "string", "minLength": 2, "maxLength": 200},
        "publisher": {"type": ["string", "null"], "maxLength": 120},
    },
}

_GUNDEM_MADDESI = {
    "type": "object",
    "required": ["importance", "title", "summary", "source"],
    "additionalProperties": False,
    "properties": {
        "importance": {"enum": ONEM_DEGERLERI},
        "title": {"type": "string", "minLength": 3, "maxLength": 160},
        "summary": {"type": "string", "minLength": 20, "maxLength": 600},
        "source": _KAYNAK,
    },
}

_TR_MADDESI = {
    "type": "object",
    "required": ["title", "summary", "source"],
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string", "minLength": 3, "maxLength": 160},
        "summary": {"type": "string", "minLength": 10, "maxLength": 600},
        "source": _KAYNAK,
    },
}

_ZAMANLI_MADDE = {
    "type": "object",
    "required": ["title"],
    "additionalProperties": False,
    "properties": {
        # Saat bilinmiyorsa null olabilir; render "—" yerine saati atlar.
        "timeTr": {"type": ["string", "null"], "pattern": r"^([01]\d|2[0-3]):[0-5]\d$"},
        "title": {"type": "string", "minLength": 3, "maxLength": 200},
    },
}

# Brief'in "Kritik" satırı için: aynı yapı, ama başlık kısa olmak zorunda —
# üç olay yan yana dizildiğinde satır hâlâ bir bakışta okunabilsin.
_KISA_ZAMANLI_MADDE = {
    "type": "object",
    "required": ["title"],
    "additionalProperties": False,
    "properties": {
        "timeTr": {"type": ["string", "null"], "pattern": r"^([01]\d|2[0-3]):[0-5]\d$"},
        "title": {"type": "string", "minLength": 3, "maxLength": 60},
    },
}

# LLM'in üretmesi beklenen bölüm. Kanonik raporun yalnızca bu kısmı modelden gelir.
LLM_SEMASI = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Günlük rapor — LLM çıktısı",
    "type": "object",
    "required": ["brief", "sections", "followUps"],
    "additionalProperties": False,
    "properties": {
        "brief": {
            "type": "object",
            "required": ["mood", "why", "criticalEvents", "mainRisk"],
            "additionalProperties": False,
            "properties": {
                "mood": {"enum": HAVA_DEGERLERI},
                "why": {"type": "string", "minLength": 20, "maxLength": 400},
                # Brief tek bakışta okunmalı: kritik olay başlıkları kısa tutulur.
                "criticalEvents": {
                    "type": "array", "maxItems": 4, "items": _KISA_ZAMANLI_MADDE,
                },
                "mainRisk": {"type": "string", "minLength": 10, "maxLength": 300},
            },
        },
        "sections": {
            "type": "object",
            "required": ["yesterday", "agenda", "today", "turkey", "risks"],
            "additionalProperties": False,
            "properties": {
                "yesterday": {
                    "type": "array", "maxItems": 6,
                    "items": {
                        "type": "object",
                        "required": ["item", "outcome"],
                        "additionalProperties": False,
                        "properties": {
                            "item": {"type": "string", "minLength": 3, "maxLength": 200},
                            "outcome": {"type": "string", "minLength": 3, "maxLength": 400},
                        },
                    },
                },
                "agenda": {"type": "array", "minItems": 1, "maxItems": 5,
                           "items": _GUNDEM_MADDESI},
                "today": {"type": "array", "maxItems": 8, "items": _ZAMANLI_MADDE},
                "turkey": {
                    "type": "object",
                    "required": ["hasNews", "items"],
                    "additionalProperties": False,
                    "properties": {
                        "hasNews": {"type": "boolean"},
                        "items": {"type": "array", "maxItems": 4, "items": _TR_MADDESI},
                    },
                },
                "risks": {
                    "type": "array", "maxItems": 3,
                    "items": {"type": "string", "minLength": 10, "maxLength": 300},
                },
            },
        },
        "followUps": {
            "type": "array", "minItems": 1, "maxItems": 5,
            "items": {"type": "string", "minLength": 5, "maxLength": 200},
        },
    },
}

# Kanonik rapor — web sitesine, Telegram'a, karta ve sese giden tek gerçek kaynak.
RAPOR_SEMASI = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://dogukanlive.com/schema/daily-report.schema.json",
    "title": "Günlük Kripto Raporu",
    "type": "object",
    "required": [
        "schemaVersion", "id", "language", "title", "publishedAt", "updatedAt",
        "status", "author", "market", "brief", "sections", "followUps",
        "sources", "assets", "disclaimer",
    ],
    "additionalProperties": False,
    "properties": {
        "schemaVersion": {"const": SEMA_SURUMU},
        # Raporun kimliği = TSİ tarihi. Aynı gün ikinci üretim yeni kayıt açmaz,
        # aynı id'yi günceller (idempotency).
        "id": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "language": {"const": "tr"},
        "title": {"type": "string", "minLength": 5, "maxLength": 200},
        "publishedAt": {"type": "string", "minLength": 20},
        "updatedAt": {"type": "string", "minLength": 20},
        "status": {"enum": ["published", "draft"]},
        "author": {
            "type": "object",
            "required": ["name", "url"],
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string", "minLength": 2},
                "url": {"type": "string", "pattern": r"^https://"},
            },
        },
        "market": {
            "type": "object",
            "required": ["asOf", "coins", "fearGreed"],
            "additionalProperties": False,
            "properties": {
                "asOf": {"type": "string", "minLength": 20},
                "coins": {
                    "type": "object",
                    "minProperties": 1,
                    "additionalProperties": {
                        "type": "object",
                        "required": ["priceUsd", "change24h"],
                        "additionalProperties": False,
                        "properties": {
                            "priceUsd": _SAYI_YA_DA_BOS,
                            "change24h": _SAYI_YA_DA_BOS,
                        },
                    },
                },
                "btcDominance": _SAYI_YA_DA_BOS,
                "ethDominance": _SAYI_YA_DA_BOS,
                "totalMarketCapUsd": _SAYI_YA_DA_BOS,
                "volume24hUsd": _SAYI_YA_DA_BOS,
                "fearGreed": {
                    "type": "object",
                    "required": ["value", "label"],
                    "additionalProperties": False,
                    "properties": {
                        "value": _TAMSAYI_YA_DA_BOS,
                        "label": {"type": ["string", "null"]},
                        "previousValue": _TAMSAYI_YA_DA_BOS,
                        "weekAgoValue": _TAMSAYI_YA_DA_BOS,
                    },
                },
            },
        },
        "brief": LLM_SEMASI["properties"]["brief"],
        "sections": LLM_SEMASI["properties"]["sections"],
        "followUps": LLM_SEMASI["properties"]["followUps"],
        # Gündem + Türkiye maddelerinin kaynakları; sayfada görünür kaynak
        # listesi olarak basılır.
        "sources": {"type": "array", "items": _KAYNAK},
        "assets": {
            "type": "object",
            "required": ["cardUrl", "audioUrl"],
            "additionalProperties": False,
            "properties": {
                # Obje depolama devreye girene kadar null. Git deposu PNG/OGG
                # ile şişmesin diye dosyalar repoda TUTULMAZ (brief §6.4).
                "cardUrl": {"type": ["string", "null"]},
                "audioUrl": {"type": ["string", "null"]},
            },
        },
        "disclaimer": {"type": "string", "minLength": 10},
    },
}


# --------------------------------------------------------------------------- #
# Doğrulama
# --------------------------------------------------------------------------- #

def _dogrula_sema(veri, sema, nerede="rapor"):
    """jsonschema varsa onu kullanır; yoksa yerleşik sade doğrulayıcıya düşer.

    jsonschema bağımlılığı requirements'ta var. Ama bot sabah 08:00'de tek
    şansa çalışıyor; kurulum eksik diye rapor hiç gitmesin istemiyoruz.
    Yerleşik doğrulayıcı aynı kuralların hepsini uygular (aşağıda)."""
    try:
        import jsonschema
    except ImportError:
        _basit_dogrula(veri, sema, nerede)
        return
    try:
        jsonschema.validate(veri, sema)
    except jsonschema.ValidationError as e:
        yol = nerede + "".join(f"[{p!r}]" for p in e.absolute_path)
        raise RaporSemaHatasi(f"{yol}: {e.message}") from None


def _basit_dogrula(veri, sema, yol):
    """jsonschema yokken devreye giren asgari doğrulayıcı.

    RAPOR_SEMASI'nda kullanılan anahtar kelimeleri destekler: type, const,
    enum, required, properties, additionalProperties, items, minItems,
    maxItems, minLength, maxLength, minProperties, pattern."""
    TIPLER = {
        "object": dict, "array": list, "string": str,
        "boolean": bool, "integer": int, "number": (int, float), "null": type(None),
    }

    def hata(mesaj):
        raise RaporSemaHatasi(f"{yol}: {mesaj}")

    if "const" in sema and veri != sema["const"]:
        hata(f"{sema['const']!r} olmalı, {veri!r} geldi")
    if "enum" in sema and veri not in sema["enum"]:
        hata(f"şunlardan biri olmalı: {sema['enum']} — {veri!r} geldi")

    if "type" in sema:
        beklenen = sema["type"]
        beklenen = beklenen if isinstance(beklenen, list) else [beklenen]
        # bool, Python'da int'in alt sınıfı; "number" beklerken True geçmesin.
        uygun = any(
            isinstance(veri, TIPLER[t]) and not (t in ("number", "integer")
                                                 and isinstance(veri, bool))
            for t in beklenen
        )
        if not uygun:
            hata(f"tip {'/'.join(beklenen)} olmalı, {type(veri).__name__} geldi")

    if isinstance(veri, str):
        if "minLength" in sema and len(veri) < sema["minLength"]:
            hata(f"en az {sema['minLength']} karakter olmalı ({len(veri)} geldi)")
        if "maxLength" in sema and len(veri) > sema["maxLength"]:
            hata(f"en fazla {sema['maxLength']} karakter olmalı ({len(veri)} geldi)")
        if "pattern" in sema and not re.search(sema["pattern"], veri):
            hata(f"biçim uymuyor ({sema['pattern']}): {veri[:60]!r}")

    if isinstance(veri, list):
        if "minItems" in sema and len(veri) < sema["minItems"]:
            hata(f"en az {sema['minItems']} öğe olmalı")
        if "maxItems" in sema and len(veri) > sema["maxItems"]:
            hata(f"en fazla {sema['maxItems']} öğe olmalı")
        if "items" in sema:
            for i, oge in enumerate(veri):
                _basit_dogrula(oge, sema["items"], f"{yol}[{i}]")

    if isinstance(veri, dict):
        if "minProperties" in sema and len(veri) < sema["minProperties"]:
            hata(f"en az {sema['minProperties']} alan olmalı")
        for alan in sema.get("required", []):
            if alan not in veri:
                hata(f"zorunlu alan eksik: {alan}")
        ozellikler = sema.get("properties", {})
        ek = sema.get("additionalProperties", True)
        for anahtar, deger in veri.items():
            if anahtar in ozellikler:
                _basit_dogrula(deger, ozellikler[anahtar], f"{yol}.{anahtar}")
            elif isinstance(ek, dict):
                _basit_dogrula(deger, ek, f"{yol}.{anahtar}")
            elif ek is False:
                hata(f"beklenmeyen alan: {anahtar}")


def dogrula(rapor):
    """Kanonik raporu şemaya ve ek yayın kurallarına göre doğrular.

    Şema geçse bile yayınlanmaması gereken durumlar var; onları burada
    yakalıyoruz (kaynak listesi tutarlılığı, tarih tutarlılığı vb.)."""
    _dogrula_sema(rapor, RAPOR_SEMASI, "rapor")

    # Kaynak listesi, metinde geçen bütün kaynakları kapsamalı — web sayfası
    # "görünür kaynak listesi"ni bu alandan basıyor.
    kullanilan = {m["source"]["url"] for m in rapor["sections"]["agenda"]}
    kullanilan |= {m["source"]["url"] for m in rapor["sections"]["turkey"]["items"]}
    listelenen = {k["url"] for k in rapor["sources"]}
    eksik = kullanilan - listelenen
    if eksik:
        raise RaporSemaHatasi(
            "rapor.sources: metinde geçen şu kaynak(lar) listede yok: "
            + ", ".join(sorted(eksik))
        )

    # publishedAt ile id aynı günü göstermeli; yoksa arşiv/sitemap karışır.
    if not rapor["publishedAt"].startswith(rapor["id"]):
        raise RaporSemaHatasi(
            f"rapor.publishedAt ({rapor['publishedAt']}) ile id ({rapor['id']}) "
            "aynı güne ait değil"
        )

    # "Türkiye'de gelişme var" deyip madde vermemek çelişkidir.
    tr = rapor["sections"]["turkey"]
    if tr["hasNews"] and not tr["items"]:
        raise RaporSemaHatasi(
            "rapor.sections.turkey: hasNews=true ama hiç madde yok"
        )
    return True


def dogrula_llm_ciktisi(veri):
    """Modelden gelen ham JSON'u, kanonik rapora gömmeden önce doğrular."""
    _dogrula_sema(veri, LLM_SEMASI, "llm")
    return True


# --------------------------------------------------------------------------- #
# Kanonik raporu kurma
# --------------------------------------------------------------------------- #

_UTM = re.compile(r"^(utm_|fbclid$|gclid$|mc_cid$|mc_eid$|ref$|source$)", re.I)


def url_temizle(url):
    """İzleme parametrelerini (utm_*, fbclid…) ve fragment'i atar.

    Aynı haber iki farklı utm ile gelince kaynak listesinde iki kez görünmesin;
    ayrıca kullanıcıyı izleyen parametreleri yeniden yayınlamayalım."""
    if not isinstance(url, str):
        return url
    parca = urlsplit(url.strip())
    sorgu = [(k, v) for k, v in parse_qsl(parca.query, keep_blank_values=True)
             if not _UTM.match(k)]
    return urlunsplit((parca.scheme, parca.netloc, parca.path,
                       urlencode(sorgu), ""))


def _kaynaklari_topla(bolumler):
    """Gündem ve Türkiye maddelerinden benzersiz kaynak listesi çıkarır (sıra korunur)."""
    kaynaklar, gorulen = [], set()
    for madde in list(bolumler["agenda"]) + list(bolumler["turkey"]["items"]):
        k = madde["source"]
        if k["url"] in gorulen:
            continue
        gorulen.add(k["url"])
        kaynaklar.append({
            "url": k["url"],
            "title": k["title"],
            "publisher": k.get("publisher"),
        })
    return kaynaklar


def rapor_kur(market, llm_ciktisi, tarih_id, baslik, simdi_iso,
              onceki_rapor=None, durum="published"):
    """LLM çıktısı + deterministik piyasa verisinden kanonik raporu üretir.

    onceki_rapor verilirse (aynı gün ikinci üretim) publishedAt korunur,
    yalnız updatedAt tazelenir — böylece aynı id yeni kayıt açmaz."""
    llm = json.loads(json.dumps(llm_ciktisi))     # çağıranın dict'ini bozma

    # Kaynak URL'lerini gömmeden önce temizle (utm vb.).
    for madde in llm["sections"]["agenda"]:
        madde["source"]["url"] = url_temizle(madde["source"]["url"])
    for madde in llm["sections"]["turkey"]["items"]:
        madde["source"]["url"] = url_temizle(madde["source"]["url"])

    return {
        "schemaVersion": SEMA_SURUMU,
        "id": tarih_id,
        "language": "tr",
        "title": baslik,
        "publishedAt": (onceki_rapor or {}).get("publishedAt", simdi_iso),
        "updatedAt": simdi_iso,
        "status": durum,
        "author": dict(VARSAYILAN_YAZAR),
        "market": market,
        "brief": llm["brief"],
        "sections": llm["sections"],
        "followUps": llm["followUps"],
        "sources": _kaynaklari_topla(llm["sections"]),
        "assets": {"cardUrl": None, "audioUrl": None},
        "disclaimer": UYARI_METNI,
    }


# --------------------------------------------------------------------------- #
# Disk düzeni — web sitesinin okuyacağı dosyalar
# --------------------------------------------------------------------------- #

KOK = os.path.dirname(os.path.abspath(__file__))
RAPORLAR_DIZINI = os.path.join(KOK, "reports")


def rapor_yollari(tarih_id):
    """(arşiv yolu, latest yolu) döndürür. Arşiv: reports/YYYY/MM/YYYY-MM-DD.json"""
    yil, ay, _ = tarih_id.split("-")
    return (
        os.path.join(RAPORLAR_DIZINI, yil, ay, f"{tarih_id}.json"),
        os.path.join(RAPORLAR_DIZINI, "latest.json"),
    )


def rapor_oku(tarih_id):
    """Aynı güne ait daha önce yazılmış rapor varsa döndürür, yoksa None."""
    arsiv, _ = rapor_yollari(tarih_id)
    try:
        with open(arsiv, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError, OSError):
        return None


def rapor_yaz(rapor):
    """Kanonik raporu arşive ve latest.json'a yazar. Yazılan yolları döndürür.

    Yazmadan önce doğrular: bozuk rapor asla diske düşmez, çünkü web sitesi
    bu dosyaları doğrudan tüketecek."""
    dogrula(rapor)
    arsiv, latest = rapor_yollari(rapor["id"])
    os.makedirs(os.path.dirname(arsiv), exist_ok=True)
    os.makedirs(os.path.dirname(latest), exist_ok=True)
    metin = json.dumps(rapor, ensure_ascii=False, indent=2) + "\n"
    for yol in (arsiv, latest):
        with open(yol, "w", encoding="utf-8") as f:
            f.write(metin)
    return arsiv, latest


def simdi_iso(dt):
    """datetime'ı ofsetli ISO-8601'e çevirir (ör. 2026-08-19T08:00:00+03:00)."""
    return dt.replace(microsecond=0).isoformat()


def sema_dosyasini_yaz():
    """JSON Schema'yı schema/daily-report.schema.json olarak dışa yazar.

    Web ekibi ingestion API'sinde aynı şemayla doğrulama yapabilsin diye
    repoda makine-okunur halde duruyor."""
    yol = os.path.join(KOK, "schema", "daily-report.schema.json")
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(RAPOR_SEMASI, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return yol


if __name__ == "__main__":
    print("şema yazıldı:", sema_dosyasini_yaz())
