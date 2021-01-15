from klarty import klarty

d = klarty()
d.connect()

# For a recognised fw file, a patch can optionally be applied
# to disable the bitstream length checking done by the FX2,
# which is part of some interlock scheme.
# Refer to the klarty python source code for details.

d.load_fx2_fw('kingst-la-01a2.fw', apply_fw_patch=False)

try:
    bcd_date = d.eeprom_read(0x20, 4)
    digits = list(d.bcd_digits(bcd_date))
    print(f'Unit purchase date: 20{digits[0]}{digits[1]}-{digits[2]}{digits[3]}')
    d.set_model_identity()
except:
    pass
