#!/usr/bin/env python3
"""Sunum ve not dosyalarını yayımlamadan önce denetler.

Kullanım:
    python3 araclar/kontrol.py h1-02          # tek konu
    python3 araclar/kontrol.py --hepsi        # hazır olan tüm konular

Çıkış kodu 0 = sorun yok, 1 = düzeltilmesi gereken hata var.
"""
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
GEREKLI_NOT_BASLIKLARI = [
    "Konunun özü",
    "Anlatım akışı",
    "Benzetmeler",
    "Güncel durum",
    "Sık sorulacak sorular",
    "Uygulama",
    "Kaynakça",
]


class SunumAyristirici(HTMLParser):
    def __init__(self):
        super().__init__()
        self.yigin = []          # açık section'lar için not bulundu mu bilgisi
        self.section_sayisi = 0
        self.notsuz = 0
        self.dis_gorsel = []
        self.lang = None
        self.tema = False
        self.reveal_js = False
        self.notes_plugin = False
        self.baglanti = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        sinif = (a.get("class") or "").split()
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "section":
            self.section_sayisi += 1
            self.yigin.append({"not": False, "ic_section": False})
            if len(self.yigin) > 1:
                self.yigin[-2]["ic_section"] = True
        elif tag == "aside" and "notes" in sinif and self.yigin:
            self.yigin[-1]["not"] = True
        elif tag == "img":
            src = a.get("src") or ""
            if not src.startswith("data:"):
                self.dis_gorsel.append(src)
        elif tag == "link" and (a.get("href") or "").endswith("assets/tema.css"):
            self.tema = True
        elif tag == "script":
            src = a.get("src") or ""
            if "reveal.js" in src and src.endswith("reveal.js"):
                self.reveal_js = True
            if "notes" in src:
                self.notes_plugin = True
        elif tag == "a" and (a.get("href") or "").startswith("http"):
            self.baglanti += 1

    def handle_endtag(self, tag):
        if tag == "section" and self.yigin:
            s = self.yigin.pop()
            # Dikey yığın kapsayıcısı (içinde section olan) not gerektirmez.
            if not s["not"] and not s["ic_section"]:
                self.notsuz += 1


def sunum_denetle(konu_id):
    hatalar, uyarilar = [], []
    yol = KOK / "sunumlar" / f"{konu_id}.html"
    if not yol.exists():
        return [f"{yol.relative_to(KOK)} yok"], uyarilar
    metin = yol.read_text(encoding="utf-8")
    p = SunumAyristirici()
    p.feed(metin)
    if "{{" in metin or "}}" in metin:
        hatalar.append("Doldurulmamış şablon alanı ({{...}}) kalmış")
    if p.lang != "tr":
        hatalar.append('<html lang="tr"> eksik')
    if not p.tema:
        hatalar.append("../assets/tema.css bağlanmamış")
    if not p.reveal_js or not p.notes_plugin:
        hatalar.append("reveal.js veya notes eklentisi yüklenmiyor")
    if p.section_sayisi < 8:
        hatalar.append(f"Slayt sayısı az: {p.section_sayisi} (en az 8)")
    if p.section_sayisi > 30:
        uyarilar.append(f"Slayt sayısı çok: {p.section_sayisi}")
    if p.notsuz:
        hatalar.append(f"{p.notsuz} slaytta konuşmacı notu (<aside class=\"notes\">) yok")
    if p.dis_gorsel:
        hatalar.append(f"Dış görsel kullanılmış (yasak): {p.dis_gorsel[:3]}")
    if p.baglanti < 3:
        hatalar.append(f"Kaynak bağlantısı az: {p.baglanti} (en az 3)")
    if "not.html?id=" not in metin:
        uyarilar.append("Anlatıcı notuna bağlantı yok")
    if "Kaynaklar" not in metin:
        hatalar.append("Kaynaklar slaytı yok")
    return hatalar, uyarilar


def not_denetle(konu_id):
    hatalar, uyarilar = [], []
    yol = KOK / "notlar" / f"{konu_id}.md"
    if not yol.exists():
        return [f"{yol.relative_to(KOK)} yok"], uyarilar
    metin = yol.read_text(encoding="utf-8")
    basliklar = re.findall(r"^##\s+(.+)$", metin, flags=re.M)
    for g in GEREKLI_NOT_BASLIKLARI:
        if not any(b.strip().startswith(g) for b in basliklar):
            hatalar.append(f"Notta '## {g}' başlığı yok")
    linkler = re.findall(r"\]\((https?://[^)]+)\)", metin)
    if len(set(linkler)) < 6:
        hatalar.append(f"Notta kaynak az: {len(set(linkler))} farklı bağlantı (en az 6)")
    kelime = len(re.findall(r"\w+", metin))
    if kelime < 1200:
        hatalar.append(f"Not kısa: {kelime} kelime (en az 1200)")
    if "{{" in metin:
        hatalar.append("Notta doldurulmamış şablon alanı var")
    return hatalar, uyarilar


def durum_denetle():
    hatalar = []
    try:
        veri = json.loads((KOK / "durum.json").read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return [f"durum.json okunamadı: {e}"]
    idler = [k["id"] for k in veri.get("konular", [])]
    if len(idler) != len(set(idler)):
        hatalar.append("durum.json içinde tekrarlanan konu kimliği var")
    return hatalar


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    veri = json.loads((KOK / "durum.json").read_text(encoding="utf-8"))
    if argv[0] == "--hepsi":
        idler = [k["id"] for k in veri["konular"] if k["durum"] in ("taslak", "gozden_gecirildi", "cilalandi")]
    else:
        idler = argv
    toplam_hata = durum_denetle()
    for h in toplam_hata:
        print(f"HATA durum.json: {h}")
    for kid in idler:
        h1, u1 = sunum_denetle(kid)
        h2, u2 = not_denetle(kid)
        for h in h1 + h2:
            print(f"HATA {kid}: {h}")
        for u in u1 + u2:
            print(f"UYARI {kid}: {u}")
        if not h1 and not h2:
            print(f"TAMAM {kid}")
        toplam_hata += h1 + h2
    return 1 if toplam_hata else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
