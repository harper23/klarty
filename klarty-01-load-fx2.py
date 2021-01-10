from klarty import *

d = klarty()
d.connect()

# For a recognised fw file, a patch can optionally be applied
# to disable the bitstream length checking done by the FX2,
# which is part of some interlock scheme.
# Refer to the klarty python source code for details.

d.load_fx2_fw('kingst-la-01a2.fw', apply_fw_patch=False)
