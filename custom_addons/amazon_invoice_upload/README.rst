======================
Amazon Invoice Uploader
======================

.. |badge1| image:: https://img.shields.io/badge/licence-LGPL--3-blue.svg
    :target: https://www.gnu.org/licenses/lgpl-3.0.html
    :alt: License: LGPL-3

|badge1|

Odoo üzerinden oluşturulan Amazon siparişlerine ait faturaları,
Amazon Selling Partner API (SP-API) aracılığıyla otomatik olarak
Amazon Seller Central'a yükleyen modüldür.

**İçindekiler**

.. contents::
   :local:

Özellikler
==========

* Fatura formunda **Amazon'a Yükle** butonu ile tek tıkla fatura gönderimi.
* Fatura PDF'i otomatik olarak oluşturulur ve Amazon Feed Document olarak yüklenir.
* ``UPLOAD_VAT_INVOICE`` feed tipi üzerinden KDV faturası meta verileri
  (sipariş numarası, fatura numarası, toplam tutar, KDV tutarı) Amazon'a iletilir.
* Fatura üzerinde **Amazon Durumu** alanı ile yükleme durumu takibi
  (Taslak / Amazon'a Gönderildi / Hata).
* **Amazon Sipariş Ref** alanı, bağlı satış siparişlerinden otomatik olarak
  hesaplanır ve fatura formunda görüntülenir.
* Birden fazla Amazon hesabına, siparişe veya marketplace'e bağlı faturalar
  için doğrulama kontrolleri yapılır.

Bağımlılıklar
=============

Bu modül aşağıdaki Odoo modüllerine bağımlıdır:

* ``base``
* ``account``
* ``sale_amazon`` — Amazon SP-API entegrasyonu ve yardımcı fonksiyonlar için.

Kurulum
=======

1. Modülü ``custom_addons`` dizinine kopyalayın.
2. Odoo'da **Uygulamalar** menüsünden modül listesini güncelleyin.
3. **Amazon Invoice Uploader** modülünü arayıp kurun.
4. ``sale_amazon`` modülünde Amazon hesap bilgilerinin (API anahtarları,
   marketplace ayarları) doğru yapılandırıldığından emin olun.

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

Teknik Detaylar
===============

Modül ``account.move`` modeline şu alanları ekler:

* ``amazon_upload_status`` — Selection alanı (draft / sent / error).
* ``amazon_order_reference`` — Computed Char alanı, bağlı satış siparişinden
  ``amazon_order_ref`` değerini alır.

Fatura formuna (``account.view_move_form``) inheritance ile:

* Başlığa **Upload to Amazon** butonu eklenir.
* ``invoice_date`` alanından sonra Amazon referans ve durum alanları gösterilir.

Bug Tracker
===========

Hataları `GitHub Issues <https://github.com/OCA/account-invoicing/issues>`_
üzerinden bildirebilirsiniz.

Credits
=======

Authors
~~~~~~~

* Odoo Community Association (OCA)

Maintainers
~~~~~~~~~~~

This module is maintained by the OCA.
