import { Mic, MicOff, PhoneOff, Video, VideoOff } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import type { CallSignal } from '../lib/types'
import { Alert, Button, Card } from './ui'

type Phase = 'idle' | 'starting' | 'calling' | 'ringing' | 'connecting' | 'live'

/**
 * A direct video call between the person and their doctor. The backend only passes the set-up messages; the video itself goes straight between the two
 * browsers. The camera and microphone are never turned on until the person clicks Start or Join, the call can always be left, and the chat stays
 * available throughout. If the camera or microphone cannot be used, nothing is lost: the conversation simply continues in chat.
 */
export default function VideoCall({
  post: postProp,
  poll: pollProp,
  otherName: otherNameProp,
}: {
  post: (kind: CallSignal['kind'], payload?: Record<string, unknown> | null) => Promise<unknown>
  poll: (after: number) => Promise<CallSignal[]>
  otherName: string
}) {
  // The parent passes new function objects on every render; keep the latest in refs so the polling loop and the handlers below stay stable.
  const postRef = useRef(postProp)
  const pollRef = useRef(pollProp)
  const nameRef = useRef(otherNameProp)
  postRef.current = postProp
  pollRef.current = pollProp
  nameRef.current = otherNameProp
  const post = useCallback((kind: CallSignal['kind'], payload?: Record<string, unknown> | null) => postRef.current(kind, payload), [])
  const poll = useCallback((after: number) => pollRef.current(after), [])
  const otherName = otherNameProp

  const [phase, setPhase] = useState<Phase>('idle')
  const [notice, setNotice] = useState('')
  const [micOn, setMicOn] = useState(true)
  const [camOn, setCamOn] = useState(true)
  const phaseRef = useRef<Phase>('idle')
  const pc = useRef<RTCPeerConnection | null>(null)
  const local = useRef<MediaStream | null>(null)
  const lastId = useRef(0)
  const pendingIce = useRef<RTCIceCandidateInit[]>([])
  const remoteSet = useRef(false)
  const localVideo = useRef<HTMLVideoElement>(null)
  const remoteVideo = useRef<HTMLVideoElement>(null)

  const go = useCallback((p: Phase) => {
    phaseRef.current = p
    setPhase(p)
  }, [])

  const teardown = useCallback(() => {
    pc.current?.close()
    pc.current = null
    local.current?.getTracks().forEach((t) => t.stop())
    local.current = null
    pendingIce.current = []
    remoteSet.current = false
    if (localVideo.current) localVideo.current.srcObject = null
    if (remoteVideo.current) remoteVideo.current.srcObject = null
    setMicOn(true)
    setCamOn(true)
  }, [])

  const getMedia = useCallback(async (): Promise<boolean> => {
    try {
      local.current = await navigator.mediaDevices.getUserMedia({ video: true, audio: true })
    } catch {
      try {
        local.current = await navigator.mediaDevices.getUserMedia({ audio: true })
        setCamOn(false)
        setNotice('Your camera could not be used, so the call is voice only.')
      } catch {
        setNotice('We could not use your camera or microphone. You can keep talking in the chat below.')
        return false
      }
    }
    if (localVideo.current) localVideo.current.srcObject = local.current
    return true
  }, [])

  const makePeer = useCallback(async () => {
    const { ice_servers } = await api.iceServers()
    const peer = new RTCPeerConnection({ iceServers: ice_servers as RTCIceServer[] })
    local.current?.getTracks().forEach((t) => peer.addTrack(t, local.current as MediaStream))
    peer.onicecandidate = (e) => {
      if (e.candidate) void post('ice', e.candidate.toJSON() as unknown as Record<string, unknown>).catch(() => undefined)
    }
    peer.ontrack = (e) => {
      if (remoteVideo.current) remoteVideo.current.srcObject = e.streams[0]
    }
    peer.onconnectionstatechange = () => {
      if (peer.connectionState === 'connected') go('live')
      if (peer.connectionState === 'failed') {
        setNotice('The call could not connect on this network. You can keep talking in the chat below.')
        void post('end').catch(() => undefined)
        teardown()
        go('idle')
      }
    }
    pc.current = peer
    return peer
  }, [go, post, teardown])

  const flushIce = useCallback(async () => {
    for (const c of pendingIce.current.splice(0)) await pc.current?.addIceCandidate(c).catch(() => undefined)
  }, [])

  const handle = useCallback(
    async (s: CallSignal) => {
      const p = phaseRef.current
      if (s.kind === 'request' && p === 'idle') {
        setNotice('')
        go('ringing')
      } else if (s.kind === 'accept' && p === 'calling') {
        go('connecting')
        const peer = await makePeer()
        const offer = await peer.createOffer()
        await peer.setLocalDescription(offer)
        await post('offer', { type: offer.type, sdp: offer.sdp })
      } else if (s.kind === 'offer' && p === 'connecting' && pc.current) {
        await pc.current.setRemoteDescription(s.payload as unknown as RTCSessionDescriptionInit)
        remoteSet.current = true
        await flushIce()
        const answer = await pc.current.createAnswer()
        await pc.current.setLocalDescription(answer)
        await post('answer', { type: answer.type, sdp: answer.sdp })
      } else if (s.kind === 'answer' && pc.current && !remoteSet.current) {
        await pc.current.setRemoteDescription(s.payload as unknown as RTCSessionDescriptionInit)
        remoteSet.current = true
        await flushIce()
      } else if (s.kind === 'ice' && s.payload) {
        if (pc.current && remoteSet.current) await pc.current.addIceCandidate(s.payload as unknown as RTCIceCandidateInit).catch(() => undefined)
        else pendingIce.current.push(s.payload as unknown as RTCIceCandidateInit)
      } else if (s.kind === 'end' || s.kind === 'decline') {
        if (p !== 'idle') setNotice(s.kind === 'decline' ? `${nameRef.current} is not able to take a video call right now. You can keep talking in the chat.` : 'The video call has ended.')
        teardown()
        go('idle')
      }
    },
    [flushIce, go, makePeer, post, teardown],
  )

  // Poll for the other side's set-up messages. Only the state of the last unanswered request matters when the page first loads.
  useEffect(() => {
    let stop = false
    let first = true
    let running = false
    const tick = async () => {
      if (running) return                       // never process two polls at once: the messages must be handled in order
      running = true
      try {
        const got = await poll(lastId.current)
        if (stop) return
        const wasFirst = first
        first = false                           // the first answer is history even when it is empty; everything after it is live
        if (got.length === 0) return
        lastId.current = got[got.length - 1].id
        if (wasFirst) {
          const last = got[got.length - 1]
          if (last.kind === 'request') await handle(last)     // only an unanswered request from before the page opened still matters
          return
        }
        for (const s of got) await handle(s)
      } catch {
        /* a failed poll is retried on the next tick */
      } finally {
        running = false
      }
    }
    void tick()
    const t = window.setInterval(() => void tick(), 1000)
    return () => {
      stop = true
      window.clearInterval(t)
    }
  }, [poll, handle])

  useEffect(() => () => teardown(), [teardown])

  async function start() {
    setNotice('')
    go('starting')
    if (!(await getMedia())) return go('idle')
    try {
      await post('request')
      go('calling')
    } catch {
      teardown()
      setNotice('The call could not be started. You can keep talking in the chat below.')
      go('idle')
    }
  }

  async function join() {
    setNotice('')
    go('starting')
    if (!(await getMedia())) {
      await post('decline').catch(() => undefined)
      return go('idle')
    }
    try {
      go('connecting')
      await makePeer()
      await post('accept')
    } catch {
      teardown()
      go('idle')
    }
  }

  async function notNow() {
    await post('decline').catch(() => undefined)
    go('idle')
  }

  async function end() {
    await post('end').catch(() => undefined)
    teardown()
    setNotice('The video call has ended.')
    go('idle')
  }

  function toggle(kind: 'audio' | 'video') {
    const tracks = kind === 'audio' ? local.current?.getAudioTracks() : local.current?.getVideoTracks()
    if (!tracks?.length) return
    const on = !tracks[0].enabled
    tracks.forEach((t) => (t.enabled = on))
    if (kind === 'audio') setMicOn(on)
    else setCamOn(on)
  }

  const inCall = phase === 'connecting' || phase === 'live' || phase === 'calling'
  return (
    <Card className="space-y-3 p-4">
      {notice && <Alert tone="info">{notice}</Alert>}

      {phase === 'idle' && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-slate-700">You can also talk by video. Your camera and microphone only turn on when you choose.</p>
          <Button onClick={() => void start()}>
            <Video className="mr-2 size-4" aria-hidden /> Start video call
          </Button>
        </div>
      )}

      {phase === 'starting' && <p className="text-sm text-slate-600">Waiting for your camera and microphone. Please allow access in your browser.</p>}

      {phase === 'ringing' && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="font-medium text-slate-900">{otherName} is asking for a video call</p>
          <div className="flex gap-2">
            <Button onClick={() => void join()}>Join</Button>
            <Button variant="secondary" onClick={() => void notNow()}>
              Not now
            </Button>
          </div>
        </div>
      )}

      {phase === 'calling' && <p className="text-sm text-slate-600">Calling {otherName}. They can choose to join or keep chatting.</p>}
      {phase === 'connecting' && <p className="text-sm text-slate-600">Connecting…</p>}

      <div className={inCall ? 'space-y-3' : 'hidden'}>
        <div className="relative overflow-hidden rounded-xl bg-slate-900">
          <video ref={remoteVideo} autoPlay playsInline className="aspect-video w-full object-cover" />
          <video ref={localVideo} autoPlay playsInline muted className="absolute bottom-2 right-2 h-24 w-32 rounded-lg border border-white/30 object-cover" />
        </div>
        <div className="flex items-center justify-center gap-3">
          <button type="button" onClick={() => toggle('audio')} aria-label={micOn ? 'Mute microphone' : 'Unmute microphone'}
            className="grid size-11 place-content-center rounded-full bg-slate-100 text-slate-800 hover:bg-slate-200">
            {micOn ? <Mic className="size-5" aria-hidden /> : <MicOff className="size-5" aria-hidden />}
          </button>
          <button type="button" onClick={() => toggle('video')} aria-label={camOn ? 'Turn camera off' : 'Turn camera on'}
            className="grid size-11 place-content-center rounded-full bg-slate-100 text-slate-800 hover:bg-slate-200">
            {camOn ? <Video className="size-5" aria-hidden /> : <VideoOff className="size-5" aria-hidden />}
          </button>
          <button type="button" onClick={() => void end()} aria-label="End call"
            className="grid size-11 place-content-center rounded-full bg-red-600 text-white hover:bg-red-700">
            <PhoneOff className="size-5" aria-hidden />
          </button>
        </div>
      </div>
    </Card>
  )
}
