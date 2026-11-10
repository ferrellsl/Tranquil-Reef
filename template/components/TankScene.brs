' Tranquil Reef: the tank's life.  Everything the build made is described in
' pkg:/data/tank.json; this file only moves it.
'
' Animated things are sprite sheets: one Poster holding every frame, slid
' behind a Group's clipping window.  (Changing a Poster's picture every frame
' made the Roku reload it, and the fish flashed; a negative scale to mirror
' them turned them upside down.  The sheets carry mirrored frames instead.)

sub init()
    m.data = ParseJson(ReadAsciiFile("pkg:/data/tank.json"))
    m.tank = m.top.findNode("tank")
    ' the tank is wider than the screen; the view pans slowly across it
    m.W = 1920
    if m.data.width <> invalid then m.W = m.data.width
    setTiles(m.top.findNode("background"), m.data.background)
    setTiles(m.top.findNode("reefMid"), m.data.reefMid)
    setTiles(m.top.findNode("reefFront"), m.data.reefFront)
    setupWater()

    m.far = m.top.findNode("farFish")
    m.near = m.top.findNode("nearFish")
    m.fish = []
    m.schools = {}
    m.visitors = []
    for each sp in m.data.species
        for i = 0 to sp.count - 1
            f = newFish(sp, i)
            m.fish.Push(f)
            if sp.DoesExist("visitor") and sp.visitor then makeVisitor(f)
        end for
    end for
    m.visitor = invalid
    m.lastVisitor = ""
    m.visitorWait = between(3, 10)

    setupCaustics()
    setupCorals()
    setupClam()
    setupRays()
    setupEel()
    setupBubbles()

    m.clock = CreateObject("roTimespan")
    m.last = m.clock.TotalMilliseconds()
    m.t = 0.0
    m.timer = m.top.findNode("tick")
    m.timer.observeField("fire", "onTick")
    m.timer.control = "start"
end sub

sub setTiles(g as object, tiles as object)
    if tiles = invalid then return
    if Type(tiles) = "roAssociativeArray" then tiles = [tiles]
    if m.layers = invalid then m.layers = []
    for each t in tiles
        p = g.createChild("Poster")
        setLayer(p, t)
        m.layers.Push({ p: p, uri: t.uri })
    end for
end sub

' if the Roku runs short of texture memory it may drop a layer that never changes (the screen
' then shows only the blue behind it); load such a layer again
sub checkLayers()
    for each l in m.layers
        if l.p.loadStatus = "failed"
            print "layer reloaded: "; l.uri
            l.p.uri = ""
            l.p.uri = l.uri
        end if
    end for
end sub

' the open water's light changes slowly, deep blue to teal and back
sub setupWater()
    m.waterTint = m.top.findNode("waterTint")
    w = m.data.water
    if w = invalid then return
    m.waterTint.uri = w.uri
    m.waterTint.width = w.w
    m.waterTint.height = w.h
    m.waterTint.opacity = 0.35
    m.tints = [[60, 110, 255], [40, 200, 210], [90, 150, 255], [30, 90, 200]]
end sub

function hex2(n as integer) as string
    d = "0123456789ABCDEF"
    if n < 0 then n = 0
    if n > 255 then n = 255
    return Mid(d, (n \ 16) + 1, 1) + Mid(d, (n mod 16) + 1, 1)
end function

sub moveWater(t as float)
    if m.tints = invalid then return
    n = m.tints.Count()
    period = 40.0
    f = t / period
    k = Int(f) mod n
    w = f - Int(f)
    w = w * w * (3 - 2 * w)
    a = m.tints[k]
    b = m.tints[(k + 1) mod n]
    r = Int(a[0] + (b[0] - a[0]) * w)
    g = Int(a[1] + (b[1] - a[1]) * w)
    bl = Int(a[2] + (b[2] - a[2]) * w)
    m.waterTint.blendColor = "0x" + hex2(r) + hex2(g) + hex2(bl) + "FF"
end sub

sub setLayer(p as object, info as object)
    p.uri = info.uri
    p.width = info.w
    p.height = info.h
    p.translation = [info.x, info.y]
end sub

' ------------------------------------------------------------------ sprites

function newSprite(parent as object, info as object) as object
    g = parent.createChild("Group")
    g.clippingRect = [0, 0, info.w, info.h]
    p = g.createChild("Poster")
    p.uri = info.sheet
    p.width = info.sheetW
    p.height = info.sheetH
    return { g: g, p: p, info: info, cur: -1 }
end function

sub setFrame(spr as object, k as integer)
    if k = spr.cur then return
    spr.cur = k
    i = spr.info
    spr.p.translation = [-(k mod i.cols) * i.pitchX, -(k \ i.cols) * i.pitchY]
end sub

function between(a as float, b as float) as float
    return a + (b - a) * Rnd(0)
end function

' ------------------------------------------------------------------ fish

function newFish(sp as object, i as integer) as object
    f = { sp: sp, frame: between(0, sp.frames), dir: -1, turning: false, turnT: 0.0, away: false, leaving: false }
    if sp.role = "cruiser"
        f.d = between(0.15, 0.35)
    else if sp.role = "school"
        if m.schools[sp.name] = invalid
            sc = { name: sp.name, x: between(300, m.W - 300), y: between(250, 600), dir: -1, tx: 900, ty: 400, d: between(0.25, 0.85) }
            pickTarget(sc, sc.d)
            m.schools[sp.name] = sc
        end if
        f.school = m.schools[sp.name]
        f.dOff = between(-0.08, 0.08)
        f.d = f.school.d + f.dOff
        f.ox = between(-170, 170)
        f.oy = between(-70, 70)
    else
        f.d = between(0.30, 1.0)
    end if
    if f.d < 0 then f.d = 0
    if f.d > 1 then f.d = 1
    f.s = 0.42 + 0.58 * f.d
    if f.d < 0.62
        f.spr = newSprite(m.far, sp)
        f.spr.g.opacity = 1.0
    else
        f.spr = newSprite(m.near, sp)
    end if
    f.spr.g.scaleRotateCenter = [sp.w / 2, sp.h / 2]
    f.spr.g.scale = [f.s, f.s]
    f.far = f.d < 0.62
    f.spk = between(0.8, 1.2)
    f.speed = sp.speed * (0.7 + 0.5 * f.d) * f.spk
    if sp.role = "cruiser"
        f.away = between(15, 60)
        f.x = -2000
        f.y = 400
        f.spr.g.visible = false
    else
        f.x = between(100, m.W - 100)
        f.y = between(200, 700)
        if Rnd(0) < 0.5 then f.dir = 1
        pickTarget(f, f.d)
    end if
    return f
end function

' a new depth for a fish: its size and speed follow, and it moves to the layer behind or in
' front of the reef.  Only done while it is out of sight (off the screen, or out of the tank).
' (Depth used to be chosen once at the start: a fish drawn into the back stayed there all session.)
sub setDepth(f as object, d as float)
    if d < 0 then d = 0
    if d > 1 then d = 1
    f.d = d
    f.s = 0.42 + 0.58 * d
    f.speed = f.sp.speed * (0.7 + 0.5 * d) * f.spk
    g = f.spr.g
    g.scale = [f.s, f.s]
    far = d < 0.62
    if far <> f.far
        if f.far then m.far.removeChild(g) else m.near.removeChild(g)
        if far then m.far.appendChild(g) else m.near.appendChild(g)
        f.far = far
    end if
end sub

' out of sight on the screen just now (the tank is wider than the screen and pans)
function offScreen(x as float) as boolean
    sx = x + m.tank.translation[0]
    return sx < -260 or sx > 1920 + 260
end function

sub pickTarget(f as object, d as float)
    ' far fish keep to the open water above the distant sand line
    if d < 0.62
        ' behind the reef: keep at reef height, so they are seen passing behind corals
        f.ty = between(380, 820)
    else
        f.ty = between(150, 820)
    end if
    f.tx = between(-150, m.W + 150)
end sub

sub onTick()
    now = m.clock.TotalMilliseconds()
    dt = (now - m.last) / 1000.0
    m.last = now
    if dt > 0.2 then dt = 0.2
    m.t = m.t + dt
    t = m.t

    ' the view pans slowly across the tank and back (about a minute and a half each way)
    span = m.W - 1920
    if span > 0
        m.tank.translation = [-span * (0.5 - 0.5 * Cos(t * 6.2832 / 180.0)), 0]
    else
        m.tank.translation = [-20 + 14 * Sin(t / 97.0), -11 + 8 * Sin(t / 131.0)]
    end if
    moveWater(t)
    if Int(t / 3) <> Int((t - dt) / 3) then checkLayers()

    for each key in m.schools
        moveLeader(m.schools[key], dt)
    end for
    moveVisitors(dt)
    for each f in m.fish
        if not f.away and f.school = invalid and not f.turning and f.sp.role <> "cruiser" and not f.leaving
            if offScreen(f.x) and Rnd(0) < dt * 0.05
                setDepth(f, between(0.30, 1.0))
                pickTarget(f, f.d)
            end if
        end if
        if f.away
            ' (a visitor out of the tank: nothing to draw)
        else if f.sp.role = "cruiser"
            moveCruiser(f, dt)
        else
            moveFish(f, dt)
        end if
    end for
    moveCaustics(dt)
    moveCorals(dt)
    moveClam(dt)
    moveRays(t)
    moveEel(dt)
    moveBubbles(dt)
end sub

sub moveLeader(sc as object, dt as float)
    if offScreen(sc.x - 200) and offScreen(sc.x + 200) and Rnd(0) < dt * 0.05
        sc.d = between(0.25, 0.85)
        for each f in m.fish
            if f.school <> invalid and f.sp.name = sc.name then setDepth(f, sc.d + f.dOff)
        end for
        pickTarget(sc, sc.d)
    end if
    dx = sc.tx - sc.x
    if Abs(dx) < 60 or Rnd(0) < dt * 0.05 then pickTarget(sc, sc.d)
    if dx > 0 then sc.x = sc.x + 90 * dt else sc.x = sc.x - 90 * dt
    sc.y = sc.y + (sc.ty - sc.y) * dt * 0.4
end sub

sub moveFish(f as object, dt as float)
    sp = f.sp
    if f.school <> invalid
        f.tx = f.school.x + f.ox
        f.ty = f.school.y + f.oy
    end if
    dx = f.tx - f.x
    dy = f.ty - f.y
    vx = 0.0
    vy = 0.0
    if f.turning
        f.turnT = f.turnT + dt / f.turnDur
        if f.turnT >= 1
            f.turning = false
            f.dir = -f.dir
            f.frame = 0
            vx = f.dir * f.speed * 0.75
        else
            ' a U-turn: the forward speed swings round to the other way, and the
            ' fish rises or sinks a little as it curves
            p = f.turnT
            vx = f.dir * f.speed * 0.75 * Cos(3.14159 * p)
            vy = f.turnVy * Sin(3.14159 * p)
        end if
    else
        want = 1
        if dx < 0 then want = -1
        if want <> f.dir and Abs(dx) > 60 and sp.turnFrames > 0
            f.turning = true
            f.turnT = 0
            f.turnDur = sp.turnTime * between(0.85, 1.25)
            f.turnVy = between(-0.25, 0.25) * f.speed
        else
            ' (they cruise on: slowing down before a turn looked like stopping)
            ease = Abs(dx) / 200.0
            if ease > 1 then ease = 1
            if ease < 0.75 then ease = 0.75
            vx = f.dir * f.speed * ease
            lim = f.speed * 0.35
            vy = dy * 0.6
            if vy > lim then vy = lim
            if vy < -lim then vy = -lim
            if f.school = invalid and not f.leaving and (Abs(dx) < 50 or Rnd(0) < dt * 0.03) then pickTarget(f, f.d)
        end if
    end if
    f.x = f.x + vx * dt
    f.y = f.y + vy * dt

    g = f.spr.g
    n = sp.frames
    s = f.s
    if f.turning
        k = Int(f.turnT * sp.turnFrames)
        if k > sp.turnFrames - 1 then k = sp.turnFrames - 1
        ' the turn was rendered from facing left to facing right; played
        ' backwards it turns from right to left
        if f.dir = 1 then k = sp.turnFrames - 1 - k
        setFrame(f.spr, 2 * n + k)
        g.rotation = 0
        ' swinging round toward the viewer, the fish comes a little closer
        sw = s * (1 + 0.10 * Sin(3.14159 * f.turnT))
        g.scale = [sw, sw]
    else
        g.scale = [s, s]
        rate = sp.fps * (0.45 + 0.55 * Abs(vx) / f.speed)
        f.frame = f.frame + dt * rate
        k = Int(f.frame) mod n
        if f.dir = 1 then k = k + n
        setFrame(f.spr, k)
        g.rotation = -f.dir * (vy / f.speed) * 0.25
    end if
    g.translation = [f.x - sp.w / 2, f.y - sp.h / 2]
end sub

' ------------------------------------------------------------------ visitors
' The big fish take turns: one at a time swims in from the side, stays a while, swims
' out, and its sheet is let go (uri cleared) so its texture memory is free for the next.

sub makeVisitor(f as object)
    f.away = true
    f.spr.g.visible = false
    f.spr.p.uri = ""
    m.visitors.Push(f)
end sub

sub moveVisitors(dt as float)
    if m.visitors.Count() = 0 then return
    v = m.visitor
    if v = invalid
        m.visitorWait = m.visitorWait - dt
        if m.visitorWait > 0 then return
        ' a different species from the last one, if there is a choice
        f = m.visitors[Int(Rnd(0) * m.visitors.Count())]
        if m.visitors.Count() > 1
            while f.sp.name = m.lastVisitor
                f = m.visitors[Int(Rnd(0) * m.visitors.Count())]
            end while
        end if
        f.spr.p.uri = f.sp.sheet
        f.spr.cur = -1
        f.turning = false
        setDepth(f, between(0.45, 1.0))       ' (fresh each visit, mostly in front of the reef)
        if Rnd(0) < 0.5
            f.dir = 1
            f.x = -250
            f.tx = between(m.W * 0.35, m.W - 200)
        else
            f.dir = -1
            f.x = m.W + 250
            f.tx = between(200, m.W * 0.65)
        end if
        if f.far then f.y = between(400, 780) else f.y = between(250, 700)
        f.ty = f.y
        f.stay = between(70, 140)
        f.leaving = false
        f.away = false
        f.spr.g.visible = true
        m.visitor = f
        if f.far then print "visitor: "; f.sp.name; " (behind the reef)" else print "visitor: "; f.sp.name; " (in front)"
        return
    end if
    v.stay = v.stay - dt
    if v.stay <= 0 and not v.leaving
        ' out by the nearer side
        v.leaving = true
        if v.x < m.W / 2 then v.tx = -450 else v.tx = m.W + 450
        v.ty = v.y
    end if
    if v.leaving and (v.x < -300 or v.x > m.W + 300)
        v.spr.g.visible = false
        v.spr.p.uri = ""
        v.away = true
        v.leaving = false
        m.lastVisitor = v.sp.name
        m.visitor = invalid
        m.visitorWait = between(4, 15)
    end if
end sub

sub moveCruiser(f as object, dt as float)
    sp = f.sp
    g = f.spr.g
    if not g.visible
        f.away = f.away - dt
        if f.away <= 0
            f.d = between(0.10, 0.40)
            f.s = 0.42 + 0.58 * f.d
            g.scale = [f.s, f.s]
            g.opacity = 0.55 + 0.9 * f.d
            f.y = between(220, 480)
            if Rnd(0) < 0.5
                f.dir = 1
                f.x = -sp.w * f.s
            else
                f.dir = -1
                f.x = m.W + sp.w * f.s
            end if
            f.vy = between(-8, 8)
            g.visible = true
        end if
        return
    end if
    f.x = f.x + f.dir * f.speed * dt
    f.y = f.y + f.vy * dt
    f.frame = f.frame + dt * sp.fps
    k = Int(f.frame) mod sp.frames
    if f.dir = 1 then k = k + sp.frames
    setFrame(f.spr, k)
    g.rotation = -f.dir * (f.vy / f.speed) * 0.25
    g.translation = [f.x - sp.w / 2, f.y - sp.h / 2]
    if (f.dir = 1 and f.x > m.W + sp.w) or (f.dir = -1 and f.x < -sp.w)
        g.visible = false
        f.away = between(45, 140)
    end if
end sub

' ------------------------------------------------------------------ light

sub setupCaustics()
    c = m.data.caustics
    m.caus = invalid
    if c = invalid then return
    g = m.top.findNode("caustics")
    g.translation = [c.x, c.y]
    g.scale = [c.scale, c.scale]
    ' two frames at once, the later one fading in over the earlier: the light flows.
    ' (the light's outline is in the frames and must stay over the reef: the layer
    ' only drifts a few pixels)
    m.caus = { a: newSprite(g, c), b: newSprite(g, c), f: 0.0, info: c, g: g }
end sub

sub moveCaustics(dt as float)
    if m.caus = invalid then return
    c = m.caus
    n = c.info.frames
    c.f = c.f + dt * c.info.fps
    if c.f >= n then c.f = c.f - n
    k = Int(c.f)
    setFrame(c.a, k)
    setFrame(c.b, (k + 1) mod n)
    ' a true crossfade: the outgoing frame fades out as the next fades in
    ' (keeping it at full strength made its light threads vanish all at once at each step)
    w = c.f - k
    c.a.g.opacity = 1.0 - w
    c.b.g.opacity = w
    t = m.t
    c.g.translation = [c.info.x + 2 * Sin(t * 0.37), c.info.y + 1 * Sin(t * 0.29)]
end sub

sub setupCorals()
    g = m.top.findNode("corals")
    m.corals = []
    if m.data.corals = invalid then return
    for each c in m.data.corals
        p = g.createChild("Poster")
        p.uri = c.sheet
        p.width = c.w
        p.height = c.h
        p.translation = [c.x, c.y]
        ' it sways about the middle of its base, where it grows from the rock
        p.scaleRotateCenter = [c.w / 2, c.h]
        m.corals.Push({ p: p, ph: Rnd(0) * 6.28, sp: 0.8 + 0.4 * Rnd(0) })
    end for
end sub

sub moveCorals(dt as float)
    t = m.t
    for each c in m.corals
        a = 0.022 * Sin(t * 0.9 * c.sp + c.ph) + 0.008 * Sin(t * 2.1 * c.sp + c.ph * 1.7)
        c.p.rotation = a
    end for
end sub

' ------------------------------------------------------------------ clam
' Open, its mantle gently pulsing; now and then it snaps shut, stays closed a
' moment, and opens again slowly, as giant clams do when something startles them.

sub setupClam()
    m.clam = invalid
    c = m.data.clam
    if c = invalid then return
    spr = newSprite(m.top.findNode("corals"), c)
    spr.g.translation = [c.x, c.y]
    ' a second copy on top fades in the next frame, so it moves smoothly between frames
    spr2 = newSprite(m.top.findNode("corals"), c)
    spr2.g.translation = [c.x, c.y]
    spr2.g.opacity = 0
    m.clam = { spr: spr, spr2: spr2, info: c, state: "open", t: 0.0, wait: between(25, 60), f: 0.0 }
end sub

sub moveClam(dt as float)
    if m.clam = invalid then return
    c = m.clam
    n = c.info.frames
    b = Int(n / 2) - 1     ' frames 0..b: breathing (0 = mantle swelled out); b+1..n-1: the flinch shut
    c.t = c.t + dt
    if c.state = "open"
        ' breathing, a breath every 2 s: the mantle swells out over the lips and settles back
        c.f = b / 2 - (b / 2) * Cos(c.t * 3.14159)
        c.wait = c.wait - dt
        if c.wait <= 0 then c.state = "closing"
    else if c.state = "closing"
        c.f = c.f + dt * 14.0
        if c.f >= n - 1
            c.f = n - 1
            c.state = "shut"
            c.wait = between(2, 5)
        end if
    else if c.state = "shut"
        c.wait = c.wait - dt
        if c.wait <= 0 then c.state = "opening"
    else if c.state = "opening"
        ' opens again slowly, back to the settled end of the breath
        c.f = c.f - dt * 1.4
        if c.f <= b
            c.f = b
            c.state = "open"
            c.t = 1.0                  ' (the breath carries on from there: half a breath in)
            c.wait = between(30, 80)
        end if
    end if
    if c.f < 0 then c.f = 0
    if c.f > n - 1 then c.f = n - 1
    k = Int(c.f)
    k2 = k + 1
    if k2 > n - 1 then k2 = n - 1
    setFrame(c.spr, k)
    setFrame(c.spr2, k2)
    c.spr2.g.opacity = c.f - k
end sub

sub setupRays()
    g = m.top.findNode("rays")
    m.rays = []
    for each r in m.data.rays
        p = g.createChild("Poster")
        p.uri = r
        p.width = 1920
        p.height = 1080
        m.rays.Push(p)
    end for
end sub

sub moveRays(t as float)
    for i = 0 to m.rays.Count() - 1
        p = m.rays[i]
        p.opacity = 0.55 + 0.35 * Sin(t * (0.11 + 0.04 * i) + i * 2.1)
        p.translation = [25 * Sin(t * (0.045 + 0.02 * i) + i), 0]
    end for
end sub

' ------------------------------------------------------------------ moray

sub setupEel()
    e = m.data.eel
    m.eel = { info: e, state: "hidden", wait: between(4, 12), ext: e.hidden, target: e.hidden, frame: 0.0 }
    clip = m.top.findNode("eelClip")
    ' nothing of it shows left of the hole's back or below its lip
    clip.clippingRect = [e.clipX, 0, m.W - e.clipX + 40, e.clipBottom]
    m.eelSpr = newSprite(clip, e)
    ' over it: the rock rim it passes behind and the darkness inside the hole
    setLayer(m.top.findNode("eelFront"), m.data.eelFront)
    if e.DoesExist("crop")
        ' rendered in its cave: frames only, the rock already hides it where it should;
        ' a second copy on top fades in the next frame, so it moves smoothly between frames
        m.eelSpr.g.translation = [e.x, e.y]
        m.eelSpr2 = newSprite(clip, e)
        m.eelSpr2.g.translation = [e.x, e.y]
        m.eelLayer = clip
        clip.opacity = 0.004
        ' its sheet (the biggest of all) is only loaded while it is out of the hole
        m.eelSheet = e.sheet
        eelLoad(false)
        m.eel.p = 0.0
        ' the frame sequence from fully out to fully in: out pose, then the backing-in frames
        m.eelPath = [0]
        for j = 0 to e.slide - 1
            m.eelPath.Push(e.loop + j)
        end for
    end if
end sub

' frame a, or b once w passes halfway: real frames only (fading one frame into the next
' made the moray look jittery; there are enough frames now that it does not need it)
sub showEel(a as integer, b as integer, w as float)
    if w >= 0.5 then setFrame(m.eelSpr, b) else setFrame(m.eelSpr, a)
    m.eelSpr2.g.opacity = 0
end sub

' u from 0 (out) to slide (gone) along the backing-in frames
sub showEelPath(u as float)
    n = m.eelPath.Count() - 1
    if u < 0 then u = 0
    if u > n then u = n
    i = Int(u)
    j = i + 1
    if j > n then j = n
    showEel(m.eelPath[i], m.eelPath[j], u - i)
end sub

sub eelVisible(v as boolean)
    ' fade the whole moray layer rather than hiding the sprites: hidden posters let the Roku drop
    ' their texture, and after the first time it never came back
    ' (never quite 0: a layer at 0 is not drawn, so the Roku may drop its texture; 1/255 is invisible)
    if v then m.eelLayer.opacity = 1.0 else m.eelLayer.opacity = 0.004
end sub

sub eelLoad(v as boolean)
    if v then u = m.eelSheet else u = ""
    m.eelSpr.p.uri = u
    m.eelSpr2.p.uri = u
    m.eel.loaded = v
end sub

sub eelState(st as string)
    m.eel.state = st
    print "moray: "; st
end sub

' the in-scene moray: frames 0..loop-1 out of the hole turning its head, then loop..loop+slide-1
' backing into the hole; it comes out by playing those backward
sub moveEelFrames(dt as float)
    s = m.eel
    e = s.info
    if s.state = "hidden"
        s.wait = s.wait - dt
        ' load its sheet a couple of seconds before it shows
        if s.wait <= 2 and not s.loaded then eelLoad(true)
        if s.wait <= 0
            eelState("emerge")
            s.p = 0.0
            showEelPath(e.slide)
            eelVisible(true)
        end if
    else if s.state = "emerge"
        ' comes out over about 4 s, slowing as it gets there
        s.p = s.p + dt / 4.0
        q = s.p
        if q >= 1
            eelState("stay")
            s.frame = 0.0
            s.wait = between(12, 30)
            showEel(0, 1, 0)
        else
            q = 1 - (1 - q) * (1 - q)
            showEelPath(e.slide * (1 - q))
        end if
    else if s.state = "stay"
        s.frame = s.frame + dt * e.fps
        if s.frame >= e.loop then s.frame = s.frame - e.loop
        k = Int(s.frame)
        showEel(k, (k + 1) mod e.loop, s.frame - k)
        s.wait = s.wait - dt
        ' back in once its head is round to the start of the turn again (where the backing-in frames start)
        if s.wait <= 0 and k = e.loop - 1
            eelState("retreat")
            s.p = 0.0
        end if
    else if s.state = "retreat"
        ' backs in over about 3 s, easing in and out
        s.p = s.p + dt / 3.0
        if s.p >= 1
            eelState("hidden")
            s.wait = between(15, 40)
            eelVisible(false)
            eelLoad(false)
        else
            q = s.p
            showEelPath(e.slide * q * q * (3 - 2 * q))
        end if
    end if
end sub

sub moveEel(dt as float)
    s = m.eel
    e = s.info
    if e.DoesExist("crop")
        moveEelFrames(dt)
        return
    end if
    if s.state = "hidden"
        s.wait = s.wait - dt
        if s.wait <= 0
            s.state = "out"
            s.target = between(e.outMin, e.outMax)
        end if
    else if s.state = "out"
        ' slides out of the hole, slowing as it gets there
        s.ext = s.ext + (s.target - s.ext) * dt * 0.45
        if Abs(s.target - s.ext) < 1
            s.state = "stay"
            s.wait = between(10, 25)
        end if
    else if s.state = "stay"
        s.wait = s.wait - dt
        ' now and then it leans a little further out or back
        if Rnd(0) < dt * 0.12 then s.target = between(e.outMin, e.outMax)
        s.ext = s.ext + (s.target - s.ext) * dt * 0.3
        if s.wait <= 0 then s.state = "in"
    else if s.state = "in"
        ' and backs into it again
        s.ext = s.ext + (e.hidden - 6 - s.ext) * dt * 0.6
        if s.ext <= e.hidden
            s.ext = e.hidden
            s.state = "hidden"
            s.wait = between(12, 35)
        end if
    end if
    s.frame = s.frame + dt * e.fps
    setFrame(m.eelSpr, Int(s.frame) mod e.frames)
    m.eelSpr.g.translation = [e.x + s.ext, e.y - s.ext * 0.25]
end sub

' ------------------------------------------------------------------ bubbles

sub setupBubbles()
    g = m.top.findNode("bubbles")
    m.bub = []
    src = m.data.bubbleSource
    for i = 0 to 55
        p = g.createChild("Poster")
        p.uri = "pkg:/images/bubble.png"
        sz = between(4, 15)
        p.width = sz
        p.height = sz
        m.bub.Push({ node: p, y: src[1] - between(0, src[1] - 30), v: between(110, 210), ph: between(0, 6.28), sz: sz, dx: between(-7, 7) })
    end for
end sub

sub moveBubbles(dt as float)
    src = m.data.bubbleSource
    for each b in m.bub
        b.y = b.y - b.v * dt
        b.ph = b.ph + dt * 4.0
        if b.y < 20
            b.y = src[1] - between(0, 20)
            b.v = between(110, 210)
            b.dx = between(-7, 7)
        end if
        ' the column wanders a little as it rises; small bubbles wobble more
        x = src[0] + b.dx + 6 * Sin(b.ph) * (16 - b.sz) / 12 + 10 * Sin(b.y * 0.006 + m.t * 0.3)
        b.node.translation = [x, b.y]
        if b.y < 160 then b.node.opacity = 0.8 * (b.y - 20) / 140.0 else b.node.opacity = 0.8
    end for
end sub
