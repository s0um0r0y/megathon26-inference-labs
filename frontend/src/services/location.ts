// GPS position plus compass heading and phone pitch. Heading lets the backend say
// "on your right" instead of a compass bearing; pitch drives the "raise the phone" cue.

import type { GeoFix } from './api';

export interface Orientation {
  heading?: number; // degrees clockwise from north, where the back camera points
  pitch?: number; // DeviceOrientation beta: ~90 = phone upright, ~0 = flat
}

type OrientationEventWithCompass = DeviceOrientationEvent & { webkitCompassHeading?: number };

export class LocationTracker {
  private fix: GeoFix | null = null;
  private orientation: Orientation = {};
  private watchId: number | null = null;
  private readonly onOrientation = (e: Event) => this.handleOrientation(e as OrientationEventWithCompass);

  /** Resolves with the first fix, or rejects if permission is denied. */
  start(): Promise<GeoFix> {
    return new Promise((resolve, reject) => {
      if (!('geolocation' in navigator)) return reject(new Error('Geolocation unsupported'));
      let first = true;
      this.watchId = navigator.geolocation.watchPosition(
        (p) => {
          this.fix = {
            lat: p.coords.latitude,
            lon: p.coords.longitude,
            accuracy_m: Math.round(p.coords.accuracy),
          };
          if (first) {
            first = false;
            resolve(this.fix);
          }
        },
        (err) => first && reject(err),
        { enableHighAccuracy: true, maximumAge: 10_000, timeout: 20_000 },
      );
      // Android Chrome: 'deviceorientationabsolute' is relative to north; plain
      // 'deviceorientation' alpha is relative to the start position.
      window.addEventListener('deviceorientationabsolute', this.onOrientation);
      window.addEventListener('deviceorientation', this.onOrientation);
    });
  }

  stop() {
    if (this.watchId !== null) navigator.geolocation.clearWatch(this.watchId);
    window.removeEventListener('deviceorientationabsolute', this.onOrientation);
    window.removeEventListener('deviceorientation', this.onOrientation);
  }

  private handleOrientation(e: OrientationEventWithCompass) {
    const o: Orientation = { pitch: e.beta ?? undefined };
    if (typeof e.webkitCompassHeading === 'number') {
      o.heading = e.webkitCompassHeading;
    } else if (e.absolute && e.alpha !== null) {
      // alpha is counter-clockwise; with the phone upright the back camera faces
      // the same way as the top of a flat phone, so this is the camera heading.
      o.heading = (360 - e.alpha) % 360;
    } else {
      o.heading = this.orientation.heading;
    }
    this.orientation = o;
  }

  current(): GeoFix | undefined {
    if (!this.fix) return undefined;
    const { heading } = this.orientation;
    return heading === undefined ? this.fix : { ...this.fix, heading_deg: Math.round(heading) % 360 };
  }

  pitch(): number | undefined {
    return this.orientation.pitch;
  }
}
