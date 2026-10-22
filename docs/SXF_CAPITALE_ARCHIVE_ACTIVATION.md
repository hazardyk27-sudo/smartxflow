# SXF CAPİTALE — Tek girişli güvenli arşivleme bağlantısı

Kapsam: SmartXFlow admin arşiv paneli `/admin/sxf-archive`; hedef depo `hazardyk27-sudo/capitale`.
**Supabase yalnızca SELECT; hiçbir ham veri silinmez veya değiştirilmez.**

## A. Admin girişi

Bu sürüm, eski `SUPABASE_URL` + herkese açık `SUPABASE_ANON_KEY` yöntemini *sadece geçici legacy admin erişimi* için korur. Böyle açılmış oturumla **GitHub arşivlemesi başlatılamaz**.

Yetkili sunucu operatörü güvenli SSH/terminal oturumunda:

```bash
cd /opt/smartxflow
sudo /opt/smartxflow/venv/bin/python scripts/configure_sxf_archive_access.py
```

Betik (1) en az 16 karakterli **yeni ve yalnız yöneticinin bildiği şifreyi** iki kez ister ve yalnız `scrypt` hash'ini `/opt/smartxflow/.env` dosyasına ekler; (2) fine-grained CAPİTALE GitHub token'ını gizli girişle alır; (3) başka ortam anahtarlarını korur. İzinler `0600`; sırları terminale yazdırmaz. Sonra:

```bash
sudo /opt/smartxflow/venv/bin/python scripts/configure_sxf_archive_access.py --check
sudo systemctl restart smartxflow-web
```

**Admin panelinde ikinci PIN/kilit yoktur.** `/admin/login` tek şifreli oturuma geçer; daha önce açılmış legacy oturumlar GitHub arşivleme başlatamaz. Yeni şifre kullanılıp yeniden giriş yapılmalı. Şifre veya token sohbete, public repoya ya da terminal komut satırına yazılmamalı.

## B. Yalnız CAPİTALE Actions token'ı

GitHub token oluşturma: `https://github.com/settings/personal-access-tokens/new`

- Resource owner: `hazardyk27-sudo` (ilgili hesap)
- Repository access: **Only selected repositories** → `capitale`
- Repository permissions: **Actions → Read and write**; metadata as required/read only
- Kısa son kullanma tarihi, başka repo veya `Contents:write` izni verme

Bu token sadece CAPİTALE repo'sunun `sxf-admin-archive.yml` workflow'unu başlatmak/okumak için sunucuda `CAPITALE_GITHUB_ACTIONS_TOKEN` adıyla kullanılır. Arşivlere dosya yükleme GitHub Actions'ın kendi repo-scoped `GITHUB_TOKEN` yetkisiyle olur.

## C. Kaynak için gerçekten salt okunur PostgreSQL DSN

Veritabanı yöneticisi mevcut `research_archive` şemasına **yalnız CONNECT / USAGE / SELECT** veren ayrı bir LOGIN rolüyle DSN sağlamalı. Bu kurulum arşiv göçü sırasında Supabase DDL/DML izni vermez ve hiçbir SQL yazma komutu çalıştırmaz.

**Admin/owner, `postgres`, `service_role`, anonim istemci anahtarı veya yazma yetkisi bulunan bağlantı kullanılmaz.** Veritabanı kaynağını okumak için `SXF_ARCHIVE_DATABASE_URL` PostgreSQL DSN'si GitHub Actions özel sırrı olmalı:

`https://github.com/hazardyk27-sudo/capitale/settings/secrets/actions` → **New repository secret** → adı **SXF_ARCHIVE_DATABASE_URL**.

GitHub'dan indirilecek arşivlerin bütünlüğü ayrıca gzip + JSONL, satır sayısı, SHA-256 ve indirilen asset byte karşılaştırması ile denetlenir.

## D. Kabul testi

- Önce 2026-10-09, **Konsantre Arşiv**; sonra **Tüm Snapshotlar**.
- GitHub Actions `https://github.com/hazardyk27-sudo/capitale/actions/workflows/sxf-admin-archive.yml` üzerinden ilgili run gerçekten `success` olmalı.
- Kaynak inventory ve günlük `COMPLETE/PARTIAL` bayrağına sadık kalınmalı.
- GitHub'da draft Release + `verification_receipt.json` ve günlük append-only receipt varlığı sorgulanmalı; *yalnız kuyruğa alındı* durumu hiçbir zaman `arşiv tamamlandı` değildir.
- Bütün ilk doğrulamalar geçmeden toplu günler başlatılmamalı.

## Ortam durumu ve sınırlar

Canlı sunucuya yönetim erişimi ayrı ayrı doğrulanır. GitHub bağlantı token'ı veya gerçekten SELECT-only DB kimliği otomatik olarak üretilmiş varsayılamaz. GitHub plugin mevcut ortamda Actions repository secret yazma aracı sunmaz. `Supabase` konektörü üzerinden hiçbir veritabanı yazması yapılmayacak.
