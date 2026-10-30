# SPDX-FileCopyrightText: Simon Schneegans <code@simonschneegans.de>
# SPDX-FileCopyrightText: 2026 SwipeTree contributors
# SPDX-License-Identifier: MIT
"""Python adaptation of Kando's pause/corner gesture detector, with explicit time.

Source: kando-menu/kando@63c2502c11d31ca709c6496642745c75dc37e8a2
src/menu-renderer/input-methods/gesture-detector.ts. See assets/kando-MIT.txt.
No Qt timers in the recognizer: UI and tests supply monotonic timestamps.
"""
from dataclasses import dataclass
import math


@dataclass
class GestureDetector:
    minimum: float = 74.
    angle: float = 38.
    jitter: float = 7.
    pause_ms: int = 240
    start: tuple | None = None
    end: tuple | None = None
    due: float | None = None

    def reset(self, point=None):
        self.start = self.end = point
        self.due = None

    def motion(self, point, now):
        point = tuple(point)
        if self.start is None:
            self.reset(point)
            return None
        sx,sy = self.end[0]-self.start[0], self.end[1]-self.start[1]
        length = math.hypot(sx,sy)
        tx,ty = point[0]-self.end[0],point[1]-self.end[1]
        tip = math.hypot(tx,ty)
        if length > self.minimum:
            if tip > self.jitter:
                self.due = None
                cosine = max(-1.,min(1.,(tx*sx+ty*sy)/(tip*length)))
                if math.degrees(math.acos(cosine)) > self.angle:
                    selected = self.end
                    self.reset(selected)
                    return selected
                self.end = point
            if self.due is None:
                self.due = now + self.pause_ms/1000
        else:
            self.end = point
            if math.dist(self.start,point) > self.minimum:
                self.due = now + self.pause_ms/1000
        return None

    def poll(self, now):
        if self.due is not None and now >= self.due:
            point = self.end
            self.reset(point)
            return point
        return None


def clamp_center(point, width, height, radius):
    """Qt logical coordinates; clamp independently on every monitor."""
    margin_x,margin_y = min(radius,width/2),min(radius,height/2)
    return (max(margin_x,min(width-margin_x,point[0])),
            max(margin_y,min(height-margin_y,point[1])))


def item_angles(count, incoming=None, root=False):
    if root:
        # Convert / process never change direction when Save/Review become available.
        return (180.,0.,-90.,90.)[:count]
    if not count:
        return ()
    if incoming is None:
        return tuple(-90+i*360/count for i in range(count))
    # Reserve the rear arc for the parent; spread children into the chosen direction.
    spread = min(240.,max(90.,(count-1)*48.))
    return tuple(incoming-spread/2+i*spread/max(1,count-1) for i in range(count)) if count>1 else (incoming,)


def hit_sector(point, center, angles, dead_zone=38., outer=190., incoming=None):
    dx,dy=point[0]-center[0],point[1]-center[1]
    distance=math.hypot(dx,dy)
    if distance <= dead_zone:
        return -2
    if not angles or distance > outer:
        return -1
    angle=math.degrees(math.atan2(dy,dx))
    def difference(a,b):
        return abs((a-b+180)%360-180)
    if incoming is not None and difference(angle,incoming+180) < 40:
        return -3
    return min(range(len(angles)),key=lambda i:difference(angle,angles[i]))
