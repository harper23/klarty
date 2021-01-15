from klarty import klarty, LA_models

d = klarty()
d.connect()

d.set_model_identity() # Set FPGA clock rate for capture calculations

if d.model == LA_models.LA1016_R2:
    d.load_fpga_fw('kingst-LA1016-WinV3.4.3-tested.bitstream')
elif d.model == LA_models.LA2016_R2:
    d.load_fpga_fw('kingst-LA2016-WinV3.4.3-tested.bitstream')
else:
    raise ValueError('FixMe: not sure which bitstream to load')

print('Set defaults:')

d.get_run_state()
run_state = d.get_run_state()
if run_state != 0x85E9:
    print(f'WARNING run_state is 0x{run_state:04x} but should be 0x85E9')

d.threshold(1.65)

# User PWM default settings
pwm1_Hz = 1e3
pwm1_dutypc = 50
pwm2_Hz = 100e3
pwm2_dutypc = 50
d.user_pwm_enable(0,0) # Disable both user PWM outputs
d.user_pwm_settings(1, pwm1_Hz, pwm1_dutypc)
d.user_pwm_settings(2, pwm2_Hz, pwm2_dutypc)
d.user_pwm_enable(1,1) # Enable both user PWM outputs

print('EEPROM:')
d.print_ascii_hex(d.eeprom_read(0x20,4))
d.print_ascii_hex(d.eeprom_read(0x08,8))

print('KAuth serial response:')
d.kauth_read_serial()
print('KAuth challenge response:')
d.kauth_authenticate()

