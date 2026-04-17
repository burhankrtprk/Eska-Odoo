import json
import logging
import re
from lxml import etree

from requests import Session
from zeep import Client, Settings, Transport
from zeep.helpers import serialize_object
from zeep.plugins import HistoryPlugin
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

ARAS_ORDER_URL = {
    'prod': "https://customerws.araskargo.com.tr/arascargoservice.asmx?WSDL",
    'test': "https://customerservicestest.araskargo.com.tr/arascargoservice/arascargoservice.asmx?WSDL",
}

ARAS_QUERY_URL = {
    'prod': "https://customerservices.araskargo.com.tr/"
            "ArasCargoCustomerIntegrationService/ArasCargoIntegrationService.svc?singleWsdl",
    'test': "https://customerservicestest.araskargo.com.tr/"
            "ArasCargoIntegrationService.svc?singleWsdl",
}

CANCEL_RESULT_MESSAGES = {
    '0': 'Successful',
    '1': 'Successfully deleted.',
    '-1': 'Record not found.',
    '-2': 'Invalid username or password.',
    '936': 'An error occurred.',
    '999': 'Cannot cancel a dispatched order.',
}


class ArasShippingClient:

    def __init__(self, username, password, customer_code='', environment='test', env=None):
        self.username = username
        self.password = password
        self.customer_code = customer_code
        self.aras_env = 'prod' if environment == 'prod' else 'test'
        self.env = env

        session = Session()
        session.timeout = 30
        self.transport = Transport(session=session)
        self.history = HistoryPlugin(maxlen=10)
        self.settings = Settings(strict=False, xml_huge_tree=True)

        self._order_client = None
        self._query_client = None

    @property
    def order_client(self):
        if self._order_client is None:
            self._order_client = self._build_client(ARAS_ORDER_URL[self.aras_env])
        return self._order_client

    @property
    def query_client(self):
        if self._query_client is None:
            self._query_client = self._build_client(ARAS_QUERY_URL[self.aras_env])
        return self._query_client

    def _build_client(self, wsdl_url):
        try:
            return Client(
                wsdl=wsdl_url,
                transport=self.transport,
                settings=self.settings,
                plugins=[self.history],
            )
        except Exception as e:
            _logger.error("Aras WSDL connection error (%s): %s", wsdl_url, e)
            return None

    def _log_soap_exchange(self, operation):
        try:
            if self.history.last_sent:
                raw = etree.tostring(self.history.last_sent['envelope'], pretty_print=True)
                _logger.debug("Aras SOAP [%s] REQUEST:\n%s", operation, raw.decode('utf-8'))

            if self.history.last_received:
                raw = etree.tostring(self.history.last_received['envelope'], pretty_print=True)
                _logger.debug("Aras SOAP [%s] RESPONSE:\n%s", operation, raw.decode('utf-8'))

        except Exception:
            _logger.debug("Failed to log SOAP exchange for %s", operation, exc_info=True)

    @staticmethod
    def _get_result_field(result, field, default=''):
        if isinstance(result, dict):
            return result.get(field, default)
        return getattr(result, field, default)

    @staticmethod
    def _serialize_for_log(payload):
        try:
            serialized = serialize_object(payload)
        except Exception:
            serialized = payload

        text = str(serialized)
        return text[:1500]

    @classmethod
    def is_missing_record_response(cls, payload):
        if not payload:
            return False
        text = cls._serialize_for_log(payload).lower()
        return 'kayıt bulunamadı' in text or 'kayit bulunamadi' in text

    def create_order(self, order_data):
        client = self.order_client
        if not client:
            raise UserError(self.env._("Could not connect to Aras Kargo shipping service."))
        try:
            pieces = order_data.pop('PieceDetails', None)
            if pieces:
                order_data['PieceDetails'] = {'PieceDetail': pieces}

            _logger.info(
                "Aras SetOrder: IntCode=%s, PieceCount=%s",
                order_data.get('IntegrationCode'),
                order_data.get('PieceCount'),
            )

            response = client.service.SetOrder(
                orderInfo={'Order': [order_data]},
                userName=self.username,
                password=self.password,
            )
            self._log_soap_exchange('SetOrder')
            _logger.info("Aras SetOrder raw response: %s", self._serialize_for_log(response))
            return self._parse_set_order_response(response)
        except UserError:
            raise
        except Exception as e:
            self._log_soap_exchange('SetOrder')
            _logger.error("SetOrder error: %s", e)
            raise UserError(self.env._("Shipping error: %s", e))

    def _parse_set_order_response(self, response):
        if response is None:
            raise UserError(self.env._("No response received from Aras Kargo (empty response)."))

        result_info = None

        if isinstance(response, list) and response:
            result_info = response[0]
        elif hasattr(response, 'OrderResultInfo') and response.OrderResultInfo:
            info = response.OrderResultInfo
            result_info = info[0] if isinstance(info, list) else info
        elif hasattr(response, 'SetOrderResult'):
            inner = response.SetOrderResult
            if hasattr(inner, 'OrderResultInfo') and inner.OrderResultInfo:
                info = inner.OrderResultInfo
                result_info = info[0] if isinstance(info, list) else info
        elif hasattr(response, 'ResultCode'):
            result_info = response

        if result_info is None:
            raise UserError(
                self.env._("Could not get a valid response from Aras Kargo.\nResponse: %s", str(response)[:300])
            )

        code = str(self._get_result_field(result_info, 'ResultCode', ''))
        message = str(self._get_result_field(result_info, 'ResultMessage', ''))
        _logger.info("Aras SetOrder result: Code=%s, Message=%s", code, message)

        if code not in ('0', '1'):
            raise UserError(self.env._("Aras Kargo Rejection (Code: %(code)s): %(message)s", code=code, message=message))
        return result_info

    def get_order_status(self, integration_code):
        client = self.order_client
        if not client:
            return None
        try:
            response = client.service.GetOrderWithIntegrationCode(
                userName=self.username,
                password=self.password,
                integrationCode=integration_code,
            )
            self._log_soap_exchange('GetOrderWithIntegrationCode')
            _logger.info(
                "Aras GetOrderWithIntegrationCode raw response for %s: %s",
                integration_code,
                self._serialize_for_log(response),
            )
            if self.is_missing_record_response(response):
                _logger.warning(
                    "Aras GetOrderWithIntegrationCode returned missing record for %s",
                    integration_code,
                )
                return None
            if isinstance(response, list) and response:
                return response[0]
            if response and hasattr(response, 'OrderResultInfo') and response.OrderResultInfo:
                return response.OrderResultInfo[0]
            return None
        except Exception as e:
            self._log_soap_exchange('GetOrderWithIntegrationCode')
            _logger.error("Aras order status query error: %s", e)
            return None

    def cancel_order(self, integration_code):
        client = self.order_client
        if not client:
            raise UserError(self.env._("Could not connect to Aras Kargo shipping service."))
        try:
            response = client.service.CancelDispatch(
                userName=self.username,
                password=self.password,
                integrationCode=integration_code,
            )
            self._log_soap_exchange('CancelDispatch')

            raw_result = str(response) if response is not None else ''
            match = re.search(r'-?\d+', raw_result)
            result_code = match.group(0) if match else ''

            if result_code in ('0', '1'):
                return {'success': True, 'message': CANCEL_RESULT_MESSAGES.get(result_code, '')}

            message = CANCEL_RESULT_MESSAGES.get(
                result_code, "Unknown cancel error (code: %s)" % result_code
            )
            return {'success': False, 'message': message}
        except Exception as e:
            self._log_soap_exchange('CancelDispatch')
            raise UserError(self.env._("Shipment cancel error: %s", e))

    def _build_login_xml(self):
        return (
            "<LoginInfo>"
            "<UserName>%s</UserName>"
            "<Password>%s</Password>"
            "<CustomerCode>%s</CustomerCode>"
            "</LoginInfo>"
        ) % (self.username, self.password, self.customer_code)

    def get_query_json(self, query_type, **kwargs):
        client = self.query_client
        if not client:
            _logger.warning("Could not connect to Aras reporting service.")
            return None

        login_info = self._build_login_xml()
        query_parts = ["<QueryType>%s</QueryType>" % query_type]
        for key, value in kwargs.items():
            query_parts.append("<%s>%s</%s>" % (key, value, key))
        query_info = "<QueryInfo>%s</QueryInfo>" % ''.join(query_parts)

        try:
            result = client.service.GetQueryJSON(
                loginInfo=login_info,
                queryInfo=query_info,
            )
            self._log_soap_exchange('GetQueryJSON(QT=%s)' % query_type)
            _logger.info(
                "Aras GetQueryJSON raw response (QT=%s): %s",
                query_type,
                self._serialize_for_log(result),
            )
            return result
        except Exception as e:
            self._log_soap_exchange('GetQueryJSON(QT=%s)' % query_type)
            _logger.warning(
                "Aras reporting error (QT=%s): %s — Falling back to shipping service.",
                query_type, e,
            )
            return None

    def query_shipment_detail(self, integration_code):
        raw = self.get_query_json(11, IntegrationCode=integration_code)
        if not raw:
            return None
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(data, list) and data:
                return data[0]
            if isinstance(data, dict):
                return data
            return None
        except (json.JSONDecodeError, TypeError):
            _logger.error("Aras QT=11 JSON parse error: %s", raw[:200] if raw else '')
            return None
