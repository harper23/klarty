from klarty import klarty
from datetime import datetime
import time

sample_rate = 1e5
sample_count = 5e5
pre_trigger_percent = 40

d = klarty()
d.connect()

d.set_model_identity() # Set FPGA clock rate for capture calculations

d.stop_sampling() # FPGAreg3 = 0x00

d.set_trigger_config() #verbose=False)
                                    
d.set_sample_config(sample_rate,sample_count,pre_trigger_percent)

d.start_acquisition()  # FPGAreg0 = 0x03

print('')
start_time = datetime.now()
msg_time=0
msg=''
last_msg=''
last_dt_ms=0
while True:
    run_state = d.get_run_state()
    run_state_mskd = 0x000F & run_state # Just use lower 4 bits
    time_delta = datetime.now() - start_time
    dt_ms = int(time_delta.total_seconds()*1000)
    if dt_ms >= 20 * 1000:
        break
    if run_state_mskd == 0x000E:
        msg = 'Running'
    elif run_state_mskd == 0x000D:
        msg = 'COMPLETE'
    elif run_state_mskd == 0x000A:
        msg = 'Waiting for trigger'
    elif run_state_mskd == 0x0002:
        msg = 'Pre-sampling'
    else:
        msg = 'Unknown state!'
    if last_msg != msg or dt_ms > (last_dt_ms+500):
        last_msg = msg
        last_dt_ms = dt_ms
        print(f'{dt_ms:8d}ms: run_state=0x{run_state:04x} {msg}')
    time.sleep(0.10)
    if run_state_mskd == 0x000D:
        break


d.stop_acquisition()  # FPGAreg1 = 0x01, FPGAreg0 = 0x00

ci = d.capture_info()

d.capture_upload(ci.n_rep_packets, ci.write_pos)
