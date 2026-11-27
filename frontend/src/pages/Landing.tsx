import { useEffect, useRef, type CSSProperties, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
// Sign in and sign-up are plain links (a full page load), so on the online demo the server's access-password page comes first.
import { LogoMark } from '../components/Brand'
import { ALL_HELPLINES, EMERGENCY, HELPLINES } from '../lib/helplines'
import './landing.css'

/*
 * The public landing page: what anyone sees at "/" before signing in. Signed-in people never see it (AppLayout sends them into the app).
 * Every claim matches what IRIS does; the prototype notice is on the first screen and in the footer.
 */

const delay = (s: number) => ({ '--d': `${s}s` }) as CSSProperties

const Check = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden>
    <path d="M20 6 9 17l-5-5" />
  </svg>
)

const PhoneIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden>
    <path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z" />
  </svg>
)

const RULES: { title: string; text: string; icon: ReactNode }[] = [
  {
    title: 'Helplines at once',
    text: 'A worrying message, even in Hinglish, shows the call buttons and alerts the team.',
    icon: <path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />,
  },
  {
    title: 'A person decides',
    text: 'Software only sorts the queue. It never closes a case or tells you that you are fine.',
    icon: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
  },
  {
    title: 'No false promises',
    text: 'IRIS never says a doctor is coming, or when, until one has accepted.',
    icon: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  },
  {
    title: 'Private and logged',
    text: 'Only the care team can read what you share, and every record they open is logged.',
    icon: <><rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></>,
  },
]

const TEAM = [
  'A queue sorted by priority, with an instant alert for urgent messages',
  'Reviewers can raise a priority, never lower it',
  'Doctors read a short summary, then chat or call by video',
]

/** Reveal on scroll, once: sections rise and fade in the first time they come into view. Reduced motion: everything simply shows. */
function useReveal(root: React.RefObject<HTMLDivElement | null>) {
  useEffect(() => {
    const el = root.current
    if (!el || window.matchMedia('(prefers-reduced-motion: reduce)').matches || !('IntersectionObserver' in window)) return
    el.classList.add('js')
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => {
        if (e.isIntersecting) {
          e.target.classList.add('shown')
          io.unobserve(e.target)
        }
      }),
      { rootMargin: '0px 0px -8% 0px', threshold: 0.12 },
    )
    el.querySelectorAll('[data-reveal]').forEach((t) => io.observe(t))
    return () => io.disconnect()
  }, [root])
}

export default function Landing() {
  const root = useRef<HTMLDivElement>(null)
  useReveal(root)

  return (
    <div ref={root} className="lp">
      <a className="skip" href="#main">Skip to content</a>
      <div className="strip">
        In crisis or need to talk now? Call <a href="tel:14416">Tele-MANAS 14416</a> (free, 24×7) or <a href="tel:112">112</a>.
      </div>

      <header>
        <div className="wrap">
          <a className="logo" href="#main" aria-label="IRIS home">
            <LogoMark className="mark size-[34px]" />
            <b>IRIS</b>
          </a>
          <div className="links">
            <a href="#how">How it works</a>
            <a href="#safety">Safety</a>
            <a href="#team">Care team</a>
          </div>
          <nav className="nav" aria-label="Main">
            <Link className="em" to="/emergency"><PhoneIcon />Emergency<span className="long"> help</span></Link>
            <span className="sep" aria-hidden />
            <a className="signin" href="/login">Sign in</a>
            <a className="btn primary sm" href="/register"><span className="long">Create an account</span><span className="short">Sign up</span></a>
          </nav>
        </div>
      </header>

      <main id="main">
        {/* Hero */}
        <section className="hero" aria-labelledby="lp-h1">
          <div className="wrap in">
            <div>
              <span className="tag">Student wellbeing support</span>
              <h1 id="lp-h1">Mental-health support for college students</h1>
              <p className="sub">
                A short check-in, a chat that answers straight away, and a team that reads every message. When you need more, a doctor can talk with you.
              </p>
              <div className="acts">
                <a className="btn primary" href="/register">Create an account</a>
                <a className="btn secondary" href="#how">See how it works</a>
              </div>
              <ul className="facts">
                <li><Check />6-minute check-in</li>
                <li><Check />Every message read by a person</li>
                <li><Check />Helplines one tap away</li>
              </ul>
              <p className="note">Academic prototype. Not yet clinically reviewed.</p>
            </div>
            <div className="frame" role="img" aria-label="The IRIS chat: a student writes about exam stress and IRIS replies with an idea and a question">
              <div className="bar"><span><i />Talk to IRIS</span><small>Today</small></div>
              <div className="chat">
                <div className="me">Exams are next week and I can&rsquo;t sleep properly.</div>
                <div className="reply">
                  <p style={{ color: 'var(--ink)' }}>It sounds like the exams are weighing on you and making it hard to rest. What part of it feels heaviest right now?</p>
                  <p><b style={{ color: 'var(--ink)' }}>A wind-down routine.</b> Try 20 minutes without screens before bed, with the same small routine each night.</p>
                  <p className="ai">Written by an AI assistant. A person on our team still reads your message.</p>
                  <div className="rate">Did this help? <span>Yes</span><span>Not really</span></div>
                </div>
                <div className="status"><i />A person on our team is reading this now.</div>
              </div>
              <div className="composer">Write here <b aria-hidden>↑</b></div>
            </div>
          </div>
        </section>

        {/* How it works */}
        <section id="how" className="block alt" aria-labelledby="lp-how">
          <div className="wrap">
            <h2 id="lp-how" data-reveal>How IRIS helps</h2>
            <p className="intro" data-reveal style={delay(0.08)}>Three steps, at your own pace. Nothing is shared with a doctor unless you agree.</p>
            <div className="grid3">
              <article className="item" data-reveal style={delay(0.1)}>
                <div className="vis" aria-hidden><div className="ui">
                  <div className="prog"><i className="on" /><i className="on" /><i className="on" /><i /><i /><i /></div>
                  <div className="q">Trouble falling or staying asleep?</div>
                  <div className="opts"><span>Not at all</span><span className="on">Several days</span></div>
                </div></div>
                <div className="body">
                  <div className="head"><span className="n">1</span><h3>A 6-minute check-in</h3></div>
                  <p>Standard screening questions on mood, worry, sleep and safety. Skip any question you like.</p>
                </div>
              </article>
              <article className="item" data-reveal style={delay(0.22)}>
                <div className="vis" aria-hidden><div className="ui">
                  <span className="me">I feel so lonely at college.</span>
                  <p>Feeling alone can be hard, and it makes sense to say so. <b>One small social step</b> could help.</p>
                  <div className="ai2">A person on our team still reads your message.</div>
                </div></div>
                <div className="body">
                  <div className="head"><span className="n">2</span><h3>Talk to IRIS</h3></div>
                  <p>Write in your own words and get a reply straight away. A person on the team reads every message.</p>
                </div>
              </article>
              <article className="item" data-reveal style={delay(0.34)}>
                <div className="vis" aria-hidden><div className="ui">
                  <div className="doc"><span className="av">K</span><span><b>Dr. Kavya Menon</b><small>Clinical psychology</small></span></div>
                  <span className="ok">A doctor has accepted</span>
                  <div className="modes"><span>Chat</span><span>Video call</span></div>
                </div></div>
                <div className="body">
                  <div className="head"><span className="n">3</span><h3>A doctor when you need one</h3></div>
                  <p>Ask for a doctor, chat or meet by video, and see your past appointments any time.</p>
                </div>
              </article>
            </div>
          </div>
        </section>

        {/* Safety */}
        <section id="safety" className="safety" aria-labelledby="lp-safe">
          <div className="wrap two">
            <div>
              <h2 id="lp-safe" data-reveal>Safety comes first</h2>
              <p className="intro" data-reveal style={delay(0.08)}>IRIS is designed so that nothing worrying is left to software alone.</p>
              <ul className="rules">
                {RULES.map((r, i) => (
                  <li key={r.title} data-reveal="left" style={delay(0.1 + i * 0.1)}>
                    <span className="ic">
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>{r.icon}</svg>
                    </span>
                    <div><b>{r.title}</b>{r.text}</div>
                  </li>
                ))}
              </ul>
            </div>
            <div className="ustage" data-reveal="right" style={delay(0.15)} role="img" aria-label="An urgent message: IRIS shows the helplines straight away">
              <div className="frame urgent">
                <div className="bar"><span><i />Talk to IRIS</span><small>Now</small></div>
                <div className="ubody">
                  <span className="me">I don&rsquo;t want to be here anymore.</span>
                  <h4>We are concerned about how you are feeling, and you do not have to go through this alone.</h4>
                  <p className="lead">Please contact one of these now, even if it feels hard.</p>
                  <div className="lines">
                    {[...HELPLINES, EMERGENCY].map((h) => (
                      <a key={h.tel} className="line" href={`tel:${h.tel}`} tabIndex={-1}>
                        <i>&#9743;</i><span><b>{h.number}</b><small>{h.tel === EMERGENCY.tel ? 'Emergency' : h.name}</small></span>
                      </a>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Care team */}
        <section id="team" className="block" aria-labelledby="lp-team">
          <div className="wrap two">
            <div>
              <h2 id="lp-team" data-reveal>Tools for reviewers and doctors</h2>
              <p className="intro" data-reveal style={delay(0.08)}>The care team sees the most urgent cases first and keeps a record of every step.</p>
              <ul className="feat">
                {TEAM.map((t, i) => <li key={t} data-reveal style={delay(0.1 + i * 0.08)}><Check size={18} />{t}</li>)}
              </ul>
            </div>
            <div className="frame queue" data-reveal="zoom" style={delay(0.15)} role="img" aria-label="The reviewer's message queue, sorted by priority">
              <div className="bar"><span><i />Message queue</span><small>Sorted by priority</small></div>
              <div className="row"><span><b>Rahul V. <span className="live" aria-hidden /></b><small>Urgent · not opened yet</small></span><span className="pri h">High</span></div>
              <div className="row"><span><b>Aman G.</b><small>Flagged for review · waiting</small></span><span className="pri m">Medium</span></div>
              <div className="row"><span><b>Priya S.</b><small>Exam stress · a person is reading</small></span><span className="pri l">Low</span></div>
              <div className="row"><span><b>Neha K.</b><small>Good news · reviewed</small></span><span className="pri l">Low</span></div>
            </div>
          </div>
        </section>

        {/* Close */}
        <section className="close" aria-labelledby="lp-start">
          <div className="wrap">
            <h2 id="lp-start" data-reveal>Start with a short check-in</h2>
            <p className="intro" data-reveal style={delay(0.08)}>Create an account and answer a few questions. It takes about 6 minutes.</p>
            <div className="acts"><a className="btn primary" href="/register">Create an account</a></div>
            <div className="help" data-reveal style={delay(0.2)} aria-label="Helplines">
              {ALL_HELPLINES.map((h) => (
                <a key={h.tel} href={`tel:${h.tel}`}><b>{h.number}</b><span>{h.tel === EMERGENCY.tel ? 'Emergency' : h.name}</span></a>
              ))}
            </div>
          </div>
        </section>
      </main>

      <footer>
        <div className="wrap">
          <p>
            IRIS is an academic prototype, not yet reviewed by a clinician and not for real use. All people shown are fictional. It is not an emergency
            service: if you need help now, call 112 or Tele-MANAS 14416.
          </p>
          <nav aria-label="Footer">
            <Link to="/emergency">Emergency help</Link>
            <a href="/login">Sign in</a>
            <a href="/register">Create an account</a>
          </nav>
        </div>
      </footer>
    </div>
  )
}
