# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import platform
import unittest
from unittest import mock

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource, ResourceAttributes
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import SpanKind

from azure.monitor.opentelemetry.exporter._generated.models import ContextTagKeys
from azure.monitor.opentelemetry.exporter._quickpulse._exporter import (
    _QuickpulseExporter,
    _QuickpulseMetricReader,
)
from azure.monitor.opentelemetry.exporter._quickpulse._live_metrics import (
    enable_live_metrics,
    _QuickpulseManager,
)
from azure.monitor.opentelemetry.exporter._quickpulse._state import (
    _get_global_quickpulse_state,
    _set_global_quickpulse_state,
    _QuickpulseState,
)
from azure.monitor.opentelemetry.exporter._utils import (
    _get_sdk_version,
    _populate_part_a_fields,
)


class TestLiveMetrics(unittest.TestCase):

    @mock.patch("azure.monitor.opentelemetry.exporter._quickpulse._live_metrics._QuickpulseManager")
    def test_enable_live_metrics(self, manager_mock):
        mock_resource = mock.Mock()
        enable_live_metrics(
            connection_string="test_cs",
            resource=mock_resource,
        )
        manager_mock.assert_called_with("test_cs", mock_resource)


class TestQuickpulseManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _set_global_quickpulse_state(_QuickpulseState.PING_SHORT)

    @classmethod
    def tearDownClass(cls):
        _set_global_quickpulse_state(_QuickpulseState.OFFLINE)

    @mock.patch("opentelemetry.sdk.trace.id_generator.RandomIdGenerator.generate_trace_id")
    def test_init(self, generator_mock):
        generator_mock.return_value = "test_trace_id"
        resource = Resource.create(
            {
                ResourceAttributes.SERVICE_INSTANCE_ID: "test_instance",
                ResourceAttributes.SERVICE_NAME: "test_service",
            }
        )
        part_a_fields = _populate_part_a_fields(resource)
        qpm = _QuickpulseManager(
            connection_string="InstrumentationKey=4321abcd-5678-4efa-8abc-1234567890ac;LiveEndpoint=https://eastus.livediagnostics.monitor.azure.com/",
            resource=resource,
        )
        self.assertEqual(_get_global_quickpulse_state(), _QuickpulseState.PING_SHORT)
        self.assertTrue(isinstance(qpm._exporter, _QuickpulseExporter))
        self.assertEqual(
            qpm._exporter._live_endpoint,
            "https://eastus.livediagnostics.monitor.azure.com/",
        )
        self.assertEqual(
            qpm._exporter._instrumentation_key,
            "4321abcd-5678-4efa-8abc-1234567890ac",
        )
        self.assertEqual(qpm._base_monitoring_data_point.version, _get_sdk_version())
        self.assertEqual(qpm._base_monitoring_data_point.invariant_version, 1)
        self.assertEqual(
            qpm._base_monitoring_data_point.instance,
            part_a_fields.get(ContextTagKeys.AI_CLOUD_ROLE_INSTANCE, "")
        )
        self.assertEqual(
            qpm._base_monitoring_data_point.role_name,
            part_a_fields.get(ContextTagKeys.AI_CLOUD_ROLE, "")
        )
        self.assertEqual(qpm._base_monitoring_data_point.machine_name, platform.node())
        self.assertEqual(qpm._base_monitoring_data_point.stream_id, "test_trace_id")
        self.assertTrue(isinstance(qpm._reader, _QuickpulseMetricReader))
        self.assertEqual(qpm._reader._exporter, qpm._exporter)
        self.assertEqual(qpm._reader._base_monitoring_data_point, qpm._base_monitoring_data_point)
        self.assertTrue(isinstance(qpm._meter_provider, MeterProvider))
        self.assertEqual(qpm._meter_provider._sdk_config.metric_readers, [qpm._reader])


    def test_singleton(self):
        resource = Resource.create(
            {
                ResourceAttributes.SERVICE_INSTANCE_ID: "test_instance",
                ResourceAttributes.SERVICE_NAME: "test_service",
            }
        )
        part_a_fields = _populate_part_a_fields(resource)
        resource2 = Resource.create(
            {
                ResourceAttributes.SERVICE_INSTANCE_ID: "test_instance2",
                ResourceAttributes.SERVICE_NAME: "test_service2",
            }
        )
        qpm = _QuickpulseManager(
            connection_string="InstrumentationKey=4321abcd-5678-4efa-8abc-1234567890ac;LiveEndpoint=https://eastus.livediagnostics.monitor.azure.com/",
            resource=resource,
        )
        qpm2 = _QuickpulseManager(
            connection_string="InstrumentationKey=4321abcd-5678-4efa-8abc-1234567890ac;LiveEndpoint=https://eastus.livediagnostics.monitor.azure.com/",
            resource=resource2,
        )
        self.assertEqual(qpm, qpm2)
        self.assertEqual(
            qpm._base_monitoring_data_point.instance,
            part_a_fields.get(ContextTagKeys.AI_CLOUD_ROLE_INSTANCE, "")
        )
        self.assertEqual(
            qpm._base_monitoring_data_point.role_name,
            part_a_fields.get(ContextTagKeys.AI_CLOUD_ROLE, "")
        )
        self.assertEqual(
            qpm2._base_monitoring_data_point.instance,
            part_a_fields.get(ContextTagKeys.AI_CLOUD_ROLE_INSTANCE, "")
        )
        self.assertEqual(
            qpm2._base_monitoring_data_point.role_name,
            part_a_fields.get(ContextTagKeys.AI_CLOUD_ROLE, "")
        )

    @mock.patch("azure.monitor.opentelemetry.exporter._quickpulse._live_metrics._append_quickpulse_document")
    @mock.patch("azure.monitor.opentelemetry.exporter._quickpulse._live_metrics._get_span_document")
    @mock.patch("azure.monitor.opentelemetry.exporter._quickpulse._live_metrics._is_post_state")
    def test_record_span_server_success(self, post_state_mock, span_doc_mock, append_doc_mock):
        post_state_mock.return_value = True
        span_doc = mock.Mock()
        span_doc_mock.return_value = span_doc
        span_mock = mock.Mock()
        span_mock.end_time = 10
        span_mock.start_time = 5
        span_mock.status.is_ok = True
        span_mock.kind = SpanKind.SERVER
        qpm = _QuickpulseManager(
            connection_string="InstrumentationKey=4321abcd-5678-4efa-8abc-1234567890ac;LiveEndpoint=https://eastus.livediagnostics.monitor.azure.com/",
            resource=Resource.create(),
        )
        qpm._request_rate_counter = mock.Mock()
        qpm._request_duration = mock.Mock()
        qpm._record_span(span_mock)
        append_doc_mock.assert_called_once_with(span_doc)
        qpm._request_rate_counter.add.assert_called_once_with(1)
        qpm._request_duration.record.assert_called_once_with(5 / 1e9)

    @mock.patch("azure.monitor.opentelemetry.exporter._quickpulse._live_metrics._append_quickpulse_document")
    @mock.patch("azure.monitor.opentelemetry.exporter._quickpulse._live_metrics._get_span_document")
    @mock.patch("azure.monitor.opentelemetry.exporter._quickpulse._live_metrics._is_post_state")
    def test_record_span_server_failure(self, post_state_mock, span_doc_mock, append_doc_mock):
        post_state_mock.return_value = True
        span_doc = mock.Mock()
        span_doc_mock.return_value = span_doc
        span_mock = mock.Mock()
        span_mock.end_time = 10
        span_mock.start_time = 5
        span_mock.status.is_ok = False
        span_mock.kind = SpanKind.SERVER
        qpm = _QuickpulseManager(
            connection_string="InstrumentationKey=4321abcd-5678-4efa-8abc-1234567890ac;LiveEndpoint=https://eastus.livediagnostics.monitor.azure.com/",
            resource=Resource.create(),
        )
        qpm._request_failed_rate_counter = mock.Mock()
        qpm._request_duration = mock.Mock()
        qpm._record_span(span_mock)
        append_doc_mock.assert_called_once_with(span_doc)
        qpm._request_failed_rate_counter.add.assert_called_once_with(1)
        qpm._request_duration.record.assert_called_once_with(5 / 1e9)

    @mock.patch("azure.monitor.opentelemetry.exporter._quickpulse._live_metrics._append_quickpulse_document")
    @mock.patch("azure.monitor.opentelemetry.exporter._quickpulse._live_metrics._get_span_document")
    @mock.patch("azure.monitor.opentelemetry.exporter._quickpulse._live_metrics._is_post_state")
    def test_record_span_dep_success(self, post_state_mock, span_doc_mock, append_doc_mock):
        post_state_mock.return_value = True
        span_doc = mock.Mock()
        span_doc_mock.return_value = span_doc
        span_mock = mock.Mock()
        span_mock.end_time = 10
        span_mock.start_time = 5
        span_mock.status.is_ok = True
        span_mock.kind = SpanKind.CLIENT
        qpm = _QuickpulseManager(
            connection_string="InstrumentationKey=4321abcd-5678-4efa-8abc-1234567890ac;LiveEndpoint=https://eastus.livediagnostics.monitor.azure.com/",
            resource=Resource.create(),
        )
        qpm._dependency_rate_counter = mock.Mock()
        qpm._dependency_duration = mock.Mock()
        qpm._record_span(span_mock)
        append_doc_mock.assert_called_once_with(span_doc)
        qpm._dependency_rate_counter.add.assert_called_once_with(1)
        qpm._dependency_duration.record.assert_called_once_with(5 / 1e9)

    @mock.patch("azure.monitor.opentelemetry.exporter._quickpulse._live_metrics._append_quickpulse_document")
    @mock.patch("azure.monitor.opentelemetry.exporter._quickpulse._live_metrics._get_span_document")
    @mock.patch("azure.monitor.opentelemetry.exporter._quickpulse._live_metrics._is_post_state")
    def test_record_span_dep_failure(self, post_state_mock, span_doc_mock, append_doc_mock):
        post_state_mock.return_value = True
        span_doc = mock.Mock()
        span_doc_mock.return_value = span_doc
        span_mock = mock.Mock()
        span_mock.end_time = 10
        span_mock.start_time = 5
        span_mock.status.is_ok = False
        span_mock.kind = SpanKind.CLIENT
        qpm = _QuickpulseManager(
            connection_string="InstrumentationKey=4321abcd-5678-4efa-8abc-1234567890ac;LiveEndpoint=https://eastus.livediagnostics.monitor.azure.com/",
            resource=Resource.create(),
        )
        qpm._dependency_failure_rate_counter = mock.Mock()
        qpm._dependency_duration = mock.Mock()
        qpm._record_span(span_mock)
        append_doc_mock.assert_called_once_with(span_doc)
        qpm._dependency_failure_rate_counter.add.assert_called_once_with(1)
        qpm._dependency_duration.record.assert_called_once_with(5 / 1e9)

    @mock.patch("azure.monitor.opentelemetry.exporter._quickpulse._live_metrics._append_quickpulse_document")
    @mock.patch("azure.monitor.opentelemetry.exporter._quickpulse._live_metrics._get_log_record_document")
    @mock.patch("azure.monitor.opentelemetry.exporter._quickpulse._live_metrics._is_post_state")
    def test_record_log_exception(self, post_state_mock, log_doc_mock, append_doc_mock):
        post_state_mock.return_value = True
        log_record_doc = mock.Mock()
        log_doc_mock.return_value = log_record_doc
        log_data_mock = mock.Mock()
        attributes = {
            SpanAttributes.EXCEPTION_TYPE: "exc_type",
            SpanAttributes.EXCEPTION_MESSAGE: "exc_msg",
        }
        log_data_mock.log_record.attributes = attributes
        qpm = _QuickpulseManager(
            connection_string="InstrumentationKey=4321abcd-5678-4efa-8abc-1234567890ac;LiveEndpoint=https://eastus.livediagnostics.monitor.azure.com/",
            resource=Resource.create(),
        )
        qpm._exception_rate_counter = mock.Mock()
        qpm._record_log_record(log_data_mock)
        append_doc_mock.assert_called_once_with(log_record_doc)
        qpm._exception_rate_counter.add.assert_called_once_with(1)
