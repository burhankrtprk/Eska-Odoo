======================
Amazon Invoice Uploader
======================

|badge1|

Odoo üzerinden oluşturulan Amazon siparişlerine ait faturaları,
Amazon Selling Partner API (SP-API) aracılığıyla otomatik olarak
Amazon Seller Central'a yükleyen modüldür.

**İçindekiler**

.. contents::
   :local:

Kullanım
========

1. Amazon üzerinden gelen bir sipariş için fatura oluşturun ve onaylayın.
2. Onaylanmış fatura formunda, başlık alanında **Upload to Amazon** butonu
   görünecektir.
3. Butona tıklayın. Modül şu adımları otomatik olarak gerçekleştirir:

   a. Faturanın bağlı olduğu Amazon hesabı ve sipariş referansı tespit edilir.
   b. İlgili marketplace bilgisi belirlenir.
   c. Fatura PDF olarak render edilir.
   d. Amazon SP-API üzerinden bir Feed Document oluşturulur ve PDF yüklenir.
   e. ``UPLOAD_VAT_INVOICE`` feed'i, fatura meta verileriyle birlikte gönderilir.

4. Yükleme başarılı olursa **Amazon Durumu** ``Sent to Amazon`` olarak güncellenir.
   Hata durumunda ``Error`` olarak işaretlenir ve hata mesajı gösterilir.

.. note::

   Buton yalnızca fatura **onaylanmış** (``posted``) durumda olduğunda
   ve daha önce Amazon'a gönderilmemiş olduğunda görünür.

