' Tranquil Reef - a reef aquarium screensaver for Roku.
'
' RunScreenSaver is what Roku calls when this channel is the chosen
' screensaver; Main is what it calls when the channel is opened from the
' home screen (the same tank, to watch it).

sub Main(args as dynamic)
    ShowTank()
end sub

sub RunScreenSaver()
    ShowTank()
end sub

sub ShowTank()
    screen = CreateObject("roSGScreen")
    port = CreateObject("roMessagePort")
    screen.SetMessagePort(port)
    screen.CreateScene("TankScene")
    screen.Show()
    while true
        msg = Wait(0, port)
        if Type(msg) = "roSGScreenEvent" and msg.IsScreenClosed() then return
    end while
end sub
