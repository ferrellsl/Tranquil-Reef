' Tranquil Reef - a reef aquarium screensaver for Roku.
'
' RunScreenSaver is what Roku calls when this channel is the chosen
' screensaver; Main is what it calls when the channel is opened from the
' home screen (the same tank, to watch it).

sub Main(args as dynamic)
    ' (a memory test: launched with ?squeeze=MB, the tank leaves that much texture memory to others)
    sq = 0
    if args <> invalid and args.squeeze <> invalid then sq = Val(args.squeeze)
    ' (or with ?budget=MB: it acts as if the Roku could not load anything past that much)
    bu = 0
    if args <> invalid and args.budget <> invalid then bu = Val(args.budget)
    ShowTank(sq, bu)
end sub

sub RunScreenSaver()
    ShowTank(0, 0)
end sub

sub ShowTank(squeeze as integer, budget as integer)
    screen = CreateObject("roSGScreen")
    port = CreateObject("roMessagePort")
    screen.SetMessagePort(port)
    screen.getGlobalNode().addFields({ squeeze: squeeze, budget: budget })
    scene = screen.CreateScene("TankScene")
    screen.Show()
    while true
        msg = Wait(0, port)
        if Type(msg) = "roSGScreenEvent" and msg.IsScreenClosed() then exit while
    end while
    ' give back every texture the tank loaded, rather than leave it to the Roku: it does not always
    ' free them, and the next start of the screensaver then found its memory taken
    scene.callFunc("releaseAll")
    scene = invalid
    screen = invalid
end sub
