========================
Aras Kargo Integration
========================

Aras Kargo kargo gönderim ve raporlama entegrasyonu.

**İçindekiler**

.. contents::
   :local:

Kullanım
========

1. **Ayarlar > Envanter > Gönderi** altında yeni bir taşıyıcı oluşturun ve
   teslim türünü **Aras Kargo** seçin.
2. Aras Kargo API bilgilerini (kullanıcı adı, şifre, müşteri kodu) girin.
3. Teslimat emri onaylandığında **Aras Kargo'ya Gönder** butonuyla gönderiyi kaydedin.
4. Modül, entegrasyon kodu ve barkod numaraları oluşturarak Aras SOAP servisine
   siparişi iletir.
5. Takip numarası, barkod tarandıktan sonra otomatik olarak güncellenir.
6. Cron job ile bekleyen gönderilerin durumu periyodik olarak senkronize edilir.

