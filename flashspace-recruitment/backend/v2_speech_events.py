"""Per-connection ordering guard. Missing speech-end fails conservatively.

Do not forward a global stop signal while another utterance remains active.
Final transcript events never imply acoustic silence. Bound event memory.
"""
class SpeechEvents:
    def __init__(self):
        self.speaking=set()
        self.ended=set()
        self.finalized=set()

    def accept(self,event):
        kind=event['event'];index=event['utterance_idx']
        if index>10000:raise ValueError('Voice event budget exceeded')
        if kind in ('vad.speech_start','transcript.partial'):
            if index in self.finalized:return None
            # Partial text may arrive after VAD end. It must invalidate tentative
            # completion but must not fabricate a second acoustic start.
            if kind=='vad.speech_start':
                if index in self.ended:return None
                self.speaking.add(index)
            elif index not in self.ended:self.speaking.add(index)
        elif kind=='vad.speech_end':
            self.speaking.discard(index);self.ended.add(index)
            if self.speaking:return None
        elif kind=='transcript.final':
            if index in self.finalized:return None
            self.finalized.add(index)
        return event
