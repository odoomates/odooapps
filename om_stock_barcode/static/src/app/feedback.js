import { browser } from "@web/core/browser/browser";

/**
 * Sound and vibration for the warehouse floor: short tones made with the Web
 * Audio API (no sound files) and the vibration of phones that have one.
 */
const TONES = {
    success: [[880, 0.08]],
    location: [[660, 0.07], [990, 0.07]],
    ask: [[740, 0.09], [740, 0.09]],
    warning: [[520, 0.12], [420, 0.12]],
    error: [[220, 0.16], [0, 0.06], [180, 0.22]],
    done: [[660, 0.08], [880, 0.08], [1320, 0.16]],
};

const VIBRATIONS = {
    success: 40,
    location: [30, 40, 30],
    ask: [60, 60, 60],
    warning: [120],
    error: [200, 80, 200],
    done: [60, 60, 120],
};

let audioContext = null;

function getAudioContext() {
    const AudioContext = browser.AudioContext || browser.webkitAudioContext;
    if (!AudioContext) {
        return null;
    }
    if (!audioContext) {
        try {
            audioContext = new AudioContext();
        } catch {
            return null;
        }
    }
    if (audioContext.state === "suspended") {
        audioContext.resume().catch(() => {});
    }
    return audioContext;
}

function playTones(tones) {
    const context = getAudioContext();
    if (!context) {
        return;
    }
    let start = context.currentTime + 0.01;
    for (const [frequency, duration] of tones) {
        if (frequency) {
            const oscillator = context.createOscillator();
            const gain = context.createGain();
            oscillator.type = "square";
            oscillator.frequency.value = frequency;
            gain.gain.setValueAtTime(0.08, start);
            gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
            oscillator.connect(gain);
            gain.connect(context.destination);
            oscillator.start(start);
            oscillator.stop(start + duration);
        }
        start += duration + 0.02;
    }
}

/**
 * @param {string} kind success, location, ask, warning, error or done
 * @param {boolean} withSound
 */
export function signalScan(kind, withSound = true) {
    if (kind === "none" || !TONES[kind]) {
        return;
    }
    if (withSound) {
        playTones(TONES[kind]);
    }
    const navigator = browser.navigator;
    if (navigator && "vibrate" in navigator && withSound) {
        try {
            navigator.vibrate(VIBRATIONS[kind]);
        } catch {
            // vibration is a nice to have
        }
    }
}

/** Unlock the audio on the first touch (mobile browsers need a gesture). */
export function unlockAudio() {
    getAudioContext();
}
