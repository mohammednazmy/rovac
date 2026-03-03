import gpiod
from gpiod.line import Direction, Edge
import time
import threading
from gpiozero import PWMOutputDevice, DigitalOutputDevice
from gpiozero.pins.lgpio import LGPIOFactory

# Mapping
R_A, R_B = 17, 27
L_A, L_B = 22, 24
L_FWD, L_PWM = 20, 16
R_FWD, R_PWM = 19, 13

counts = {R_A: 0, R_B: 0, L_A: 0, L_B: 0}
running = True

def listener():
    chip_path = "/dev/gpiochip4"
    line_offsets = [R_A, R_B, L_A, L_B]
    
    try:
        with gpiod.request_lines(
            chip_path,
            consumer="encoder-final-test",
            config={
                tuple(line_offsets): gpiod.LineSettings(
                    direction=Direction.INPUT,
                    edge_detection=Edge.BOTH,
                )
            },
        ) as request:
            while running:
                if request.wait_edge_events(timeout=0.1):
                    events = request.read_edge_events()
                    for event in events:
                        counts[event.line_offset] += 1
    except Exception as e:
        print(f"Encoder thread error: {e}")

def main():
    global running
    print("Starting Unified Motor/Encoder Test...")
    
    # Start encoder thread
    t = threading.Thread(target=listener, daemon=True)
    t.start()
    
    # Setup motors
    try:
        factory = LGPIOFactory(chip=4)
        l_f = DigitalOutputDevice(L_FWD, pin_factory=factory)
        l_p = PWMOutputDevice(L_PWM, pin_factory=factory)
        r_f = DigitalOutputDevice(R_FWD, pin_factory=factory)
        r_p = PWMOutputDevice(R_PWM, pin_factory=factory)
        
        print("Driving motors forward at 50% for 3 seconds...")
        l_f.on(); l_p.value = 0.5
        r_f.on(); r_p.value = 0.5
        
        time.sleep(3)
        
        print("Stopping motors...")
        l_p.value = 0; r_p.value = 0
        l_f.off(); r_f.off()
        
        time.sleep(0.5)
        running = False
        t.join(timeout=1)
        
        print("\nFINAL TALLY:")
        print(f"Right Motor: A={counts[R_A]} ticks, B={counts[R_B]} ticks")
        print(f"Left Motor:  A={counts[L_A]} ticks, B={counts[L_B]} ticks")
        
        total = sum(counts.values())
        if total > 50:
            print("\nSUCCESS! Encoders are working via libgpiod v2.")
        else:
            print(f"\nFAILURE. Only {total} ticks detected.")
            
    except Exception as e:
        print(f"Motor error: {e}")
    finally:
        running = False

if __name__ == "__main__":
    main()
