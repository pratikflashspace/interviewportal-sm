"""Exercise the actual async bridge, not only mocked permission predicates."""
import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import backend.v2_stream as bridge

class Socket:
    def __init__(self,origin='https://test.example'):
        self.path_params={'aid':'test-application'}
        self.headers={'origin':origin,'cookie':'synthetic'}
        self.messages=[];self.accepted=False;self.closed=[]
        self.ready=asyncio.Event();self.incoming=asyncio.Queue()
    async def accept(self):self.accepted=True
    async def close(self,code):self.closed.append(code)
    async def send_json(self,message):
        self.messages.append(message)
        if message.get('event')=='ready':self.ready.set()
    async def receive(self):return await self.incoming.get()

class Upstream:
    async def send(self,message):pass
    def __aiter__(self):return self
    async def __anext__(self):
        await asyncio.Future()

class SlowClose:
    def __init__(self):self.closing=asyncio.Event();self.release=asyncio.Event()
    async def __aenter__(self):return Upstream()
    async def __aexit__(self,*args):
        self.closing.set();await self.release.wait()

class ReconnectTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        bridge.active.clear()
        self.backend=SimpleNamespace(origin='https://test.example',
            current_user=lambda env:{'id':'owner'},store=SimpleNamespace(get=lambda aid:{'user_id':'owner'}),
            flow=lambda aid:{'status':'interview'},ai_quota=lambda *args:None)
    async def test_reconnect_while_old_upstream_closes_and_late_cleanup(self):
        first,second=Socket(),Socket();old,new=SlowClose(),SlowClose();jobs=[]
        with patch.object(bridge,'backend',self.backend),patch.object(bridge,'connect',side_effect=[old,new]),patch.dict(os.environ,{'SARVAM_API_KEY':'synthetic-test-only'}):
            try:
                jobs.append(asyncio.create_task(bridge.voice(first)))
                await asyncio.wait_for(first.ready.wait(),2)
                await first.incoming.put({'type':'websocket.disconnect'})
                await asyncio.wait_for(old.closing.wait(),2)
                jobs.append(asyncio.create_task(bridge.voice(second)))
                # Legacy code rejects this connection because its guard remains
                # occupied throughout old upstream __aexit__.
                await asyncio.wait_for(second.ready.wait(),2)
                self.assertTrue(second.accepted)
                old.release.set();await asyncio.wait_for(jobs[0],2)
                # The old connection's outer finally must not remove the new lease.
                self.assertIn('test-application',bridge.active)
                third=Socket();await asyncio.wait_for(bridge.voice(third),2)
                self.assertFalse(third.accepted);self.assertIn(1008,third.closed)
                await second.incoming.put({'type':'websocket.disconnect'});new.release.set()
                await asyncio.wait_for(jobs[1],2)
                self.assertNotIn('test-application',bridge.active)
            finally:
                old.release.set();new.release.set()
                for job in jobs:job.cancel()
                await asyncio.gather(*jobs,return_exceptions=True)
                bridge.active.clear()
    async def test_live_stream_still_rejects_duplicate(self):
        first=Socket();upstream=SlowClose()
        with patch.object(bridge,'backend',self.backend),patch.object(bridge,'connect',return_value=upstream),patch.dict(os.environ,{'SARVAM_API_KEY':'synthetic-test-only'}):
            job=asyncio.create_task(bridge.voice(first))
            try:
                await asyncio.wait_for(first.ready.wait(),2)
                duplicate=Socket();await bridge.voice(duplicate)
                self.assertFalse(duplicate.accepted);self.assertEqual(duplicate.closed,[1008])
                wrong=Socket('https://wrong.example');await bridge.voice(wrong)
                self.assertFalse(wrong.accepted)
            finally:
                upstream.release.set();job.cancel();await asyncio.gather(job,return_exceptions=True);bridge.active.clear()
