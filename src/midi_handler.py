"""
MIDI input handler for the synthesizer.
Handles note on/off and other MIDI events.
"""
try:
    import mido
    MIDO_AVAILABLE = True
except ImportError:
    MIDO_AVAILABLE = False

from typing import Callable, Optional, List
import threading
import time


class MIDIHandler:
    """Handles MIDI input from connected devices."""
    
    def __init__(self):
        """Initialize the MIDI handler."""
        self.input_port = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.available = MIDO_AVAILABLE
        
        # Callbacks
        self.on_note_on: Optional[Callable[[int, int], None]] = None  # note, velocity
        self.on_note_off: Optional[Callable[[int], None]] = None  # note
        self.on_pitch_bend: Optional[Callable[[int], None]] = None  # value (-8192 to 8191)
        self.on_control_change: Optional[Callable[[int, int], None]] = None  # controller, value
        
    def list_input_ports(self) -> List[str]:
        """List all available MIDI input ports."""
        if not MIDO_AVAILABLE:
            return ['Virtual MIDI Input (No MIDI Library)']
        
        try:
            ports = mido.get_input_names()
            if not ports:
                ports = ['Virtual MIDI Input']
            return ports
        except Exception as e:
            return ['Virtual MIDI Input']
    
    def open_port(self, port_index: int = 0) -> bool:
        """
        Open a MIDI input port.
        
        Args:
            port_index: Index of the port to open (0 for virtual port if none available)
            
        Returns:
            True if successful, False otherwise
        """
        if not MIDO_AVAILABLE:
            print("Warning: Mido not available - MIDI input disabled")
            print("To enable MIDI: pip install mido")
            self.available = False
            return False
            
        try:
            ports = mido.get_input_names()
            
            if ports and port_index < len(ports):
                self.input_port = mido.open_input(ports[port_index])
                print(f"Opened MIDI port: {ports[port_index]}")
            else:
                # Open virtual port or create one
                try:
                    self.input_port = mido.open_input()
                    print("Opened default MIDI input")
                except:
                    print("Warning: Could not open MIDI input port")
                    return False
            
            return True
        except Exception as e:
            print(f"Error opening MIDI port: {e}")
            return False
    
    def start(self):
        """Start polling for MIDI messages."""
        if self.input_port is None:
            return False
        
        self.running = True
        self.thread = threading.Thread(target=self._poll_midi, daemon=True)
        self.thread.start()
        return True
    
    def stop(self):
        """Stop polling for MIDI messages."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
    
    def _poll_midi(self):
        """Poll for MIDI messages (runs in separate thread)."""
        while self.running:
            try:
                for msg in self.input_port.iter_pending():
                    self._handle_midi_message(msg)
            except:
                pass
            time.sleep(0.001)  # 1ms sleep to prevent busy waiting
    
    def _handle_midi_message(self, msg):
        """
        Handle a MIDI message.
        
        Args:
            msg: mido MidiMessage object
        """
        if msg.type == 'note_on':
            if msg.velocity > 0:
                if self.on_note_on:
                    self.on_note_on(msg.note, msg.velocity)
            else:
                # Note on with velocity 0 = Note off
                if self.on_note_off:
                    self.on_note_off(msg.note)
        
        elif msg.type == 'note_off':
            if self.on_note_off:
                self.on_note_off(msg.note)
        
        elif msg.type == 'pitchwheel':
            # mido returns -1.0 to 1.0, convert to -8192 to 8191
            value = int(msg.pitch * 8191)
            if self.on_pitch_bend:
                self.on_pitch_bend(value)
        
        elif msg.type == 'control_change':
            if self.on_control_change:
                self.on_control_change(msg.control, msg.value)
    
    def close(self):
        """Close the MIDI port."""
        self.stop()
        if self.input_port:
            self.input_port.close()
            self.input_port = None
