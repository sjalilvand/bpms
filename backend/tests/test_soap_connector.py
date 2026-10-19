# -*- coding: utf-8 -*-
"""آزمون‌های فاز ۵ — کانکتور SOAP 1.1: ساخت پوش، escape، تجزیه پاسخ و Fault."""
import pytest

from app.modules.engine import connectors


class TestEnvelope:
    def test_basic_envelope_structure(self):
        env = connectors._build_envelope({"order_id": "SO-1", "amount": 1500000})
        assert "soapenv:Envelope" in env
        assert "SOAP_NS" not in env
        assert 'xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"' in env
        assert '<arg name="order_id">SO-1</arg>' in env
        assert '<arg name="amount">1500000</arg>' in env

    def test_xml_escaping(self):
        env = connectors._build_envelope({"note": "<b>it's & \"danger\"</b>"})
        assert "<b>" not in env
        assert "&lt;b&gt;" in env
        assert "&amp;" in env

    def test_underscore_keys_and_complex_values(self):
        import json
        env = connectors._build_envelope({"_internal": 1, "items": [{"qty": 2}]})
        assert "_internal" not in env
        assert '<arg name="items">[{&quot;qty&quot;: 2}]</arg>' in env

    def test_key_sanitization(self):
        env = connectors._build_envelope({"کلید فارسی!": "v"})
        assert 'name="' in env
        assert "کلید" not in env  # نویسه‌های غیرمجاز جایگزین شده‌اند


class TestParseResponse:
    SUCCESS = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
               '<s:Body><x:executeResponse xmlns:x="http://x"><x:Result>OK-123</x:Result>'
               '</x:executeResponse></s:Body></s:Envelope>')

    FAULT = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
             '<s:Body><s:Fault><faultstring>کد نامعتبر است</faultstring></s:Fault></s:Body></s:Envelope>')

    def test_success_result(self):
        out = connectors._parse_soap_response(self.SUCCESS)
        assert out == {"result": "OK-123"}

    def test_fault_raises(self):
        with pytest.raises(RuntimeError, match="SOAP Fault"):
            connectors._parse_soap_response(self.FAULT)

    def test_invalid_xml_raises(self):
        with pytest.raises(RuntimeError, match="نامعتبر"):
            connectors._parse_soap_response("not xml at all")

    def test_unknown_body_fallback(self):
        out = connectors._parse_soap_response(
            '<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
            '<s:Body><something/></s:Body></s:Envelope>')
        assert "response_text" in out


class TestRunSoap:
    def _fake_client(self, responder):
        """httpx.Client ساختگی برای قطع شبکه."""
        class FakeResp:
            def __init__(self, status_code=200, text=""):
                self.status_code = status_code
                self.text = text

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def post(self, url, content=None, headers=None):
                FakeClient.last = {"url": url, "content": content, "headers": headers}
                return responder(FakeClient.last)

        return FakeClient

    def test_run_ok(self, monkeypatch):
        resp = self._fake_client(lambda ctx: type("R", (), {"status_code": 200, "text": self._ok()})())
        monkeypatch.setattr(connectors.httpx, "Client", resp)
        out = connectors._run("soap:http://svc.local/Order|CreateOrder", {"order_id": "SO-9"})
        assert out == {"result": "OK"}
        sent = connectors.httpx.Client.last["content"].decode("utf-8")
        assert "SO-9" in sent
        assert connectors.httpx.Client.last["headers"]["SOAPAction"] == '"CreateOrder"'

    def _ok(self):
        return ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
                '<s:Body><x:executeResponse xmlns:x="http://x"><x:Result>OK</x:Result>'
                '</x:executeResponse></s:Body></s:Envelope>')

    def test_http_error_no_retry_hang(self, monkeypatch):
        calls = {"n": 0}

        def responder(ctx):
            calls["n"] += 1
            return type("R", (), {"status_code": 500, "text": ""})()

        monkeypatch.setattr(connectors.httpx, "Client", self._fake_client(responder))
        with pytest.raises(RuntimeError, match="500"):
            connectors._run("soap:http://svc.local/Broken", {})
        assert calls["n"] == 1  # خطای ۵۰۰ بدون تلاش مجدد فوری بازمی‌گردد

    def test_execute_connector_merges_result(self, monkeypatch):
        """قرارداد کامل: نتیجه SOAP به داده وظیفه ادغام می‌شود."""
        class Spec:
            name = "Task_SOAP"

        class Task:
            data = {"order_id": "SO-7"}

        monkeypatch.setattr(connectors.httpx, "Client",
                            self._fake_client(lambda ctx: type("R", (), {"status_code": 200, "text": self._ok()})()))
        task = Task()
        task.data["_connectors"] = {"Task_SOAP": "soap:http://svc.local/X"}
        ok = connectors.execute_connector(task, Spec())
        assert ok is True
        assert task.data["_last_connector_result"] == "ok"
        assert task.data.get("result") == "OK"
