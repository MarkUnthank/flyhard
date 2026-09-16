# Flyhard: smooth roundabout cut

This replaces the choppy 20 fps slowed edit with a 25-second 1920 × 1080,
60 fps MP4. It keeps the longer camera holds, website in the black header,
request-left/right controls, requested and measured wheel angles, CARLA steering,
and stalk readout.

The A40 rendered the saved CARLA world trajectory and MuJoCo joint poses at
60 output timestamps per second. This is presentation interpolation of the same
controller episode, not another training run. Original neural measurements are
held until their next recorded sample. The cabin fly and sponsor meshes remain
depth-aware composites.

The livery was freshly downloaded from https://thedrivingfly.com immediately
before this run at 2026-09-10 07:51:08 UTC: revision 11, layout 4, seven paid
placements. Left-door and rear previews were inspected. Later advertiser changes
will be picked up by the next run; this recording retains its frozen snapshot.

Verification: all 1,500 frames decoded, 25.000 seconds at 60 fps, no repeated
adjacent road or fly frames during the 23 seconds of action. The final 2 seconds
are credits. Native replay positions stayed within 4.95 cm of the original
trajectory reference. The downloaded MP4 SHA256 matches the GPU output.

Video SHA256:
e5a5110a13a66fb9af119c15a459942509518518b51a5de021a3854e334ee0b2

The project now requires fresh live artwork before recording or rendering.
Preflight blocks stale revisions, missing paid placements, changed layouts,
altered files and cached sponsor projections from a different model. Six tests
cover these failure paths. The immutable artwork, render inputs, frame map,
native 60 fps camera video and native depth frames are retained for iteration.

Vehicle: CARLA 0.9.16, Computer Vision Center (CVC), Universitat Autònoma de Barcelona.
Connectome: MaleCNS / Janelia. Fly: NeuroMechFly / FlyGym, EPFL.
Sponsor names and artwork belong to their respective owners.

Local raw backup verified: 1,380 native depth frames (archive SHA256 4282a6bff261387160d6206e6d7e5c7abed2f1c2d7c791546e18e6047907fba3), native camera MP4, body poses and frame map.
