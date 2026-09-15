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
                lease=bridge.active['test-application']
                await second.incoming.put({'type':'websocket.disconnect'});new.release.set()
                await asyncio.wait_for(jobs[1],2)
                self.assertNotIn('test-application',bridge.active)
                self.assertTrue(lease.released.is_set())
            finally:
                old.release.set();new.release.set()
                for job in jobs:job.cancel()
                await asyncio.gather(*jobs,return_exceptions=True)
                bridge.active.clear()
    async def test_live_stream_hands_the_slot_to_the_reconnect(self):
        """A question transition closes and immediately reopens the socket."""
        first,second=Socket(),Socket();old,new=SlowClose(),SlowClose();jobs=[]
        with patch.object(bridge,'backend',self.backend),patch.object(bridge,'connect',side_effect=[old,new]),patch.dict(os.environ,{'SARVAM_API_KEY':'synthetic-test-only'}):
            try:
                jobs.append(asyncio.create_task(bridge.voice(first)))
                await asyncio.wait_for(first.ready.wait(),2)
                # The browser has not disconnected the old socket yet; the live
                # stream must still stand down so the reconnect can be served.
                jobs.append(asyncio.create_task(bridge.voice(second)))
                await asyncio.wait_for(second.ready.wait(),2)
                self.assertTrue(second.accepted)
                old.release.set();await asyncio.wait_for(jobs[0],2)
                self.assertIn('test-application',bridge.active)
                wrong=Socket('https://wrong.example');await bridge.voice(wrong)
                self.assertFalse(wrong.accepted)
            finally:
                old.release.set();new.release.set()
                for job in jobs:job.cancel()
                await asyncio.gather(*jobs,return_exceptions=True);bridge.active.clear()

    async def test_slot_that_will_not_yield_is_still_rejected(self):
        """Handover is bounded: a stuck connection must not accept a successor."""
        stuck=bridge.Lease();bridge.active['test-application']=stuck
        blocked=Socket()
        with patch.object(bridge,'backend',self.backend),patch.object(bridge,'HANDOVER_SECONDS',0.05):
            await asyncio.wait_for(bridge.voice(blocked),2)
        self.assertFalse(blocked.accepted);self.assertEqual(blocked.closed,[1008])
        self.assertIs(bridge.active.get('test-application'),stuck)
        bridge.active.clear()

    async def test_superseded_connection_before_provider_releases_the_slot(self):
        """A reconnect during a slow provider handshake is served, not refused."""
        first,second=Socket(),Socket();ready=asyncio.Event();new=SlowClose()
        class Hanging:
            async def __aenter__(self):ready.set();await asyncio.Future()
            async def __aexit__(self,*args):return False
        with patch.object(bridge,'backend',self.backend),patch.object(bridge,'connect',side_effect=[Hanging(),new]),patch.dict(os.environ,{'SARVAM_API_KEY':'synthetic-test-only'}):
            jobs=[asyncio.create_task(bridge.voice(first))]
            try:
                await asyncio.wait_for(ready.wait(),2)
                jobs.append(asyncio.create_task(bridge.voice(second)))
                await asyncio.wait_for(second.ready.wait(),2)
                await asyncio.wait_for(jobs[0],2)
                self.assertFalse(first.messages)
            finally:
                new.release.set()
                for job in jobs:job.cancel()
                await asyncio.gather(*jobs,return_exceptions=True);bridge.active.clear()
