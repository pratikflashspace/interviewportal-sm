"""No external calls: authenticated quota failures must not masquerade as network failures."""
import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import backend.v2_stream as bridge
from backend.server import APIError

class Socket:
    def __init__(self,origin='https://test.example'):
        self.path_params={'aid':'synthetic-application'}
        self.headers={'origin':origin,'cookie':'synthetic'}
        self.messages=[];self.accepted=False;self.closed=[]
    async def accept(self):self.accepted=True
    async def close(self,code):self.closed.append(code)
    async def send_json(self,message):
        if not self.accepted:raise RuntimeError('Cannot send before accept')
        self.messages.append(message)

class QuotaErrorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        bridge.active.clear()
        self.quota=Mock()
        self.backend=SimpleNamespace(origin='https://test.example',
            current_user=lambda env:{'id':'owner'},
            store=SimpleNamespace(get=lambda aid:{'id':aid,'user_id':'owner'}),
            flow=lambda aid:{'status':'interview'},ai_quota=self.quota)
    async def asyncTearDown(self):bridge.active.clear()

    async def check_failure(self,error,expected):
        self.quota.side_effect=error;socket=Socket()
        with patch.object(bridge,'backend',self.backend),patch.object(bridge,'connect') as connect:
            with self.assertLogs('flashspace.voice',level='WARNING') as logs:
                await asyncio.wait_for(bridge.voice(socket),2)
            connect.assert_not_called()
        self.assertTrue(socket.accepted)
        self.assertEqual(len(socket.messages),1)
        self.assertEqual(socket.messages[0]['event'],'error')
        self.assertEqual(socket.messages[0]['code'],expected)
        self.assertEqual(socket.closed,[1000])
        self.assertNotIn('synthetic-application',bridge.active)
        output=json.dumps(socket.messages)+' '.join(logs.output)
        self.assertNotIn('private-error-detail',output)
        self.assertNotIn('synthetic-application',output)
        self.assertIn('reason='+expected,' '.join(logs.output))
        self.quota.assert_called_once_with({'id':'synthetic-application','user_id':'owner'},'voice-session-v2',24)

    async def test_limit_reached_delivered_without_upstream(self):
        await self.check_failure(APIError(429,'private-error-detail'),'usage_limit_reached')

    async def test_database_error_not_misreported_as_limit(self):
        await self.check_failure(RuntimeError('private-error-detail'),'usage_check_unavailable')

    async def test_non_quota_api_error_not_misreported_as_limit(self):
        await self.check_failure(APIError(503,'private-error-detail'),'usage_check_unavailable')

    async def test_unauthorized_socket_never_accepted(self):
        self.backend.current_user=Mock(side_effect=APIError(401,'private-error-detail'))
        socket=Socket()
        with patch.object(bridge,'backend',self.backend),patch.object(bridge,'connect') as connect:
            await bridge.voice(socket);connect.assert_not_called()
        self.assertFalse(socket.accepted);self.assertEqual(socket.messages,[])
        self.assertEqual(socket.closed,[1008]);self.quota.assert_not_called()

    async def test_wrong_origin_never_accepted(self):
        socket=Socket('https://wrong.example')
        with patch.object(bridge,'backend',self.backend),patch.object(bridge,'connect') as connect:
            await bridge.voice(socket);connect.assert_not_called()
        self.assertFalse(socket.accepted);self.assertEqual(socket.messages,[])
        self.quota.assert_not_called()
