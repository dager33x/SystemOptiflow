"""Build Optiflow's original soft bell chimes; no downloads or audio dependency."""
from array import array
from math import exp, pi, sin, tanh
from pathlib import Path
import sys
import wave


def write_chime(path, notes, duration):
    sample_rate = 44100
    samples = array('h')
    for i in range(round(duration*sample_rate)):
        timestamp = i/sample_rate
        for channel in range(2):
            value = 0.
            for start, frequency, strength in notes:
                t = timestamp-start-channel*.004
                if t < 0:
                    continue
                attack = min(1., t/.012)
                envelope = attack*exp(-t/0.28)
                bell = (sin(2*pi*frequency*t) + .18*sin(2*pi*2*frequency*t)*exp(-t/.15)
                        + .06*sin(2*pi*3*frequency*t)*exp(-t/.10))
                value += strength*envelope*bell
            fade = min(1., max(0., (duration-timestamp)/.12))
            samples.append(round(32767*.6*tanh(value)*fade))
    if sys.byteorder != 'little':
        samples.byteswap()
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(samples.tobytes())


if __name__ == '__main__':
    target = Path(__file__).resolve().parents[1] / 'assets' / 'sounds'
    write_chime(target/'incident.wav', [(0., 659.25, .7), (.18, 830.61, .65), (.36, 987.77, .6)], 1.65)
    write_chime(target/'violation.wav', [(0., 783.99, .7), (.20, 1046.50, .6)], 1.40)
    print('Generated two original stereo bell chimes.')
