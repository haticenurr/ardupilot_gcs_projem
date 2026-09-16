# Staj Raporu

Bu klasor, projeyi anlatan staj raporunu ve raporda kullanilan gorselleri
icerir.

## Dosyalar

| Dosya | Aciklama |
|---|---|
| `STAJ_RAPORU.md` | Raporun kaynagi — duzenlemeler burada yapilir |
| `STAJ_RAPORU.docx` | Word ciktisi — teslim edilecek dosya |
| `md_to_docx.py` | MD dosyasini bicimlendirilmis Word belgesine cevirir |
| `sablon_rapor.docx` | Fakultenin resmi RP-023 sablonu (ust/alt bilgi kaynagi) |
| `gorseller/` | 16 gorsel: 11 ekran goruntusu, 5 sema ve grafik |

## Word belgesini yeniden uretme

```bash
python rapor/md_to_docx.py
```

Betik belgeyi SIFIRDAN olusturmaz: `sablon_rapor.docx` dosyasini acar ve
yalnizca govde icerigini degistirir. Bu sayede her sayfada tekrarlanan
ust bilgi (okul logosu, fakulte adi, dokuman no RP-023) ve alt bilgi
(ogrenci/yetkili ad-soyad ve imza alanlari) oldugu gibi korunur.

**Dikkat:** Betik `STAJ_RAPORU.docx` dosyasinin uzerine yazar. Word'de
elle duzenleme yapmaya basladiktan sonra betigi tekrar calistirmayin.

## Uygulanan bicim kurallari

Staj yonergesi (RP-023) geregi:

- A4 sayfa, Times New Roman, govde 11 punto
- 1,5 satir araligi, govde iki yana yasli
- Basliklar sola yasli, tek seviyeli numaralandirma (1., 2., 3.)
- Baslik girintisi asili 0,76 cm
- Paragraflar ve bolumler arasi 8 nk bosluk
- Baslik ile kendi ilk paragrafi arasinda bosluk yok
- Tablo aciklamasi tablonun USTUNDE, sekil aciklamasi seklin ALTINDA
- Metinde sekil/tablolara, gorsel yer almadan ONCE atif yapilir
- Kaynak kodlar govdede degil, EKLER bolumunde
- IEEE tarzi `[1]` atif ve kaynak listesi

## Gorseller nasil uretildi

Ekran goruntuleri, uygulamanin ekransiz (offscreen) Qt kipinde sahte bir
araca bagli calisan halinden alinmistir; elle kirpilmis ekran fotografi
degildir. Semalar ve grafikler matplotlib ile uretilmistir. Tarama
rotasi ve genisleyen kare sekilleri, projedeki gercek algoritmalarin
ciktisidir.

## Doldurulmasi gereken yerler

Raporda kirmizi italik ile isaretli uc blok bulunmaktadir:

1. Kapak bilgileri (ad, numara, bolum, tarihler, danismanlar)
2. Firmanin muhendis kadrosu ve staj yapilan birim
3. Sonuc bolumunun sonu (stajin firmaya katkisi, projenin sunumu,
   gelecek planlar)
