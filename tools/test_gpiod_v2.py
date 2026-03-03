import gpiod
from gpiod.line import Direction, Edge
import time
import threading

def encoder_listener():
    # Use the correct path for Pi 5 RP1
    chip_path = "/dev/gpiochip4"
    line_offsets = [17, 27, 22, 24]
    
    with gpiod.request_lines(
        chip_path,
        consumer="encoder-listener",
        config={
            tuple(line_offsets): gpiod.LineSettings(
                direction=Direction.INPUT,
                edge_detection=Edge.BOTH,
            )
        },
    ) as request:
        print("Listening for encoder ticks...")
        while True:
            # Wait for events with 1s timeout
            if request.wait_edge_events():
                events = request.read_edge_events()
                for event in events:
                    print(f"Tick detected on Line {event.line_offset}!")

if __name__ == "__main__":
    encoder_listener()
