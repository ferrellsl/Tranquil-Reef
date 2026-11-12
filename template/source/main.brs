' Tranquil Reef - a reef aquarium screensaver for Roku.
'
' RunScreenSaver is what Roku calls when this channel is the chosen
' screensaver.  There is no Main: a screensaver may not have one (Roku OS 16
' leaves a channel with a Main out of the screensaver list).

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
