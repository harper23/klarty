from klarty import *
from datetime import datetime

sample_rate = 1e5
sample_count = 5e5
pre_trigger_percent = 40

d = klarty()
d.connect()

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
    time_delta = datetime.now() - start_time
    dt_ms = int(time_delta.total_seconds()*1000)
    if dt_ms >= 20 * 1000:
        break
    if run_state == 0x85EE:
        msg = 'Running'
    elif run_state == 0x85ED:
        msg = 'COMPLETE'
    elif run_state == 0x85EA:
        msg = 'Waiting for trigger'
    elif run_state == 0x85E2:
        msg = 'Pre-sampling'
    else:
        msg = 'Unknown state!'
    if last_msg != msg or dt_ms > (last_dt_ms+1000):
        last_msg = msg
        last_dt_ms = dt_ms
        print(f'{dt_ms:8d}ms: run_state=0x{run_state:04x} {msg}')
    time.sleep(0.10)
    if run_state == 0x85ED:
        break


d.stop_acquisition()  # FPGAreg1 = 0x01, FPGAreg0 = 0x00

ci = d.capture_info()

d.capture_upload(ci.n_rep_packets, ci.write_pos)