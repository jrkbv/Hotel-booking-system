from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Dict, List
import json, os

DATA_FILE = "hotel_data.json"

class RoomStatus(str, Enum):
    AVAILABLE = "available"
    OCCUPIED = "occupied"
    MAINTENANCE = "maintenance"

class BookingStatus(str, Enum):
    BOOKED = "booked"
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"
    CANCELED = "canceled"

class RoomNotFoundError(ValueError): pass
class GuestNotFoundError(ValueError): pass

@dataclass
class Room:
    number: int
    room_type: str
    price_per_night: float
    status: RoomStatus = RoomStatus.AVAILABLE
    @property
    def is_occupied(self) -> bool: return self.status == RoomStatus.OCCUPIED

@dataclass
class Guest:
    guest_id: int
    name: str
    contact: str

@dataclass
class Booking:
    guest: Guest
    room: Room
    check_in_date: date
    check_out_date: date
    status: BookingStatus = BookingStatus.BOOKED
    id: int = field(default_factory=int)
    def __post_init__(self):
        if self.check_out_date <= self.check_in_date: raise ValueError("check_out_date must be after check_in_date")
    def overlaps(self, ci: date, co: date) -> bool:
        return self.check_in_date < co and ci < self.check_out_date

class Hotel:
    def __init__(self, name: str):
        self.name = name
        self._rooms: Dict[int,   Room] = {}
        self._guests: Dict[int, Guest] = {}
        self._bookings: Dict[int, Booking] = {}
        self._next_guest_id = 1
        self._next_booking_id = 1

    def add_room(self, number: int, room_type: str, price: float) -> Room:
        if number in self._rooms: raise ValueError("Room exists")
        r = Room(number, room_type, price); self._rooms[number] = r; return r

    def delete_room(self, number: int) -> None:
        if number not in self._rooms: raise RoomNotFoundError(f"Room {number} does not exist")
        for b in self._bookings.values():
            if b.room.number == number and b.status in (BookingStatus.BOOKED, BookingStatus.CHECKED_IN):
                raise ValueError("Active bookings for room")
        del self._rooms[number]

    def get_room(self, number: int) -> Room:
        if number not in self._rooms: raise RoomNotFoundError(f"Room {number} does not exist")
        return self._rooms[number]

    def list_rooms(self) -> List[Room]: return list(self._rooms.values())

    def register_guest(self, name: str, contact: str) -> Guest:
        g = Guest(self._next_guest_id, name, contact)
        self._guests[g.guest_id] = g; self._next_guest_id += 1; return g

    def delete_guest(self, guest_id: int) -> None:
        if guest_id not in self._guests: raise GuestNotFoundError(f"Guest {guest_id} does not exist")
        for b in self._bookings.values():
            if b.guest.guest_id == guest_id and b.status in (BookingStatus.BOOKED, BookingStatus.CHECKED_IN):
                raise ValueError("Active bookings for guest")
        del self._guests[guest_id]

    def get_guest(self, guest_id: int) -> Guest:
        if guest_id not in self._guests: raise GuestNotFoundError(f"Guest {guest_id} does not exist")
        return self._guests[guest_id]

    def list_guests(self) -> List[Guest]: return list(self._guests.values())

    def _check_room_available(self, room: Room, ci: date, co: date) -> None:
        for b in self._bookings.values():
            if b.room.number != room.number: continue
            if b.status in (BookingStatus.CANCELED, BookingStatus.CHECKED_OUT): continue
            if b.overlaps(ci, co): raise ValueError("Room already booked for these dates")

    def create_booking(self, guest_id: int, room_number: int, ci: date, co: date) -> Booking:
        g = self.get_guest(guest_id); r = self.get_room(room_number)
        self._check_room_available(r, ci, co)
        b = Booking(g, r, ci, co, id=self._next_booking_id)
        self._bookings[b.id] = b; self._next_booking_id += 1; return b

    def get_booking(self, booking_id: int) -> Booking:
        if booking_id not in self._bookings: raise ValueError("Booking does not exist")
        return self._bookings[booking_id]

    def cancel_booking(self, booking_id: int) -> None:
        b = self.get_booking(booking_id)
        if b.status not in (BookingStatus.BOOKED, BookingStatus.CHECKED_IN):
            raise ValueError("Cannot cancel")
        b.status = BookingStatus.CANCELED
        if b.room.is_occupied: b.room.status = RoomStatus.AVAILABLE

    def list_bookings(self) -> List[Booking]: return list(self._bookings.values())

    def check_in(self, booking_id: int, now: date) -> None:
        b = self.get_booking(booking_id)
        if b.status != BookingStatus.BOOKED: raise ValueError("Not BOOKED")
        if now != b.check_in_date: raise ValueError("Wrong date for check-in")
        if b.room.is_occupied: raise ValueError("Room occupied")
        b.status = BookingStatus.CHECKED_IN; b.room.status = RoomStatus.OCCUPIED

    def check_out(self, booking_id: int, now: date) -> float:
        b = self.get_booking(booking_id)
        if b.status != BookingStatus.CHECKED_IN: raise ValueError("Not CHECKED_IN")
        if now != b.check_out_date: raise ValueError("Wrong date for check-out")
        b.status = BookingStatus.CHECKED_OUT; b.room.status = RoomStatus.AVAILABLE
        nights = (b.check_out_date - b.check_in_date).days
        if nights <= 0: raise ValueError("Invalid dates")
        return nights * b.room.price_per_night

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "rooms": [{
                "number": r.number,
                "room_type": r.room_type,
                "price_per_night": r.price_per_night,
                "status": r.status.value
            } for r in self._rooms.values()],
            "guests": [{
                "guest_id": g.guest_id,
                "name": g.name,
                "contact": g.contact
            } for g in self._guests.values()],
            "bookings": [{
                "id": b.id,
                "guest_id": b.guest.guest_id,
                "room_number": b.room.number,
                "check_in_date": b.check_in_date.isoformat(),
                "check_out_date": b.check_out_date.isoformat(),
                "status": b.status.value
            } for b in self._bookings.values()],
            "next_guest_id": self._next_guest_id,
            "next_booking_id": self._next_booking_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Hotel":
        h = cls(d.get("name", "Hotel"))
        for r in d.get("rooms", []):
            room = Room(r["number"], r["room_type"], r["price_per_night"], RoomStatus(r["status"]))
            h._rooms[room.number] = room
        for g in d.get("guests", []):
            guest = Guest(g["guest_id"], g["name"], g["contact"])
            h._guests[guest.guest_id] = guest
        for b in d.get("bookings", []):
            guest = h._guests[b["guest_id"]]; room = h._rooms[b["room_number"]]
            book = Booking(guest, room,
                           parse_date(b["check_in_date"]),
                           parse_date(b["check_out_date"]),
                           BookingStatus(b["status"]),
                           b["id"])
            h._bookings[book.id] = book
        h._next_guest_id = d.get("next_guest_id", 1)
        h._next_booking_id = d.get("next_booking_id", 1)
        if h._bookings: h._next_booking_id = max(h._bookings.keys()) + 1
        return h

def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()

def print_menu():
    print("\n=== HOTEL MENU ===")
    print("1. Add room")
    print("2. Show rooms")
    print("3. Register guest")
    print("4. Show guests")
    print("5. Create booking")
    print("6. Show bookings")
    print("7. Cancel booking")
    print("8. Check-in")
    print("9. Check-out")
    print("10. Delete room")
    print("11. Delete guest")
    print("0. Exit")

def load_hotel() -> Hotel:
    if not os.path.exists(DATA_FILE): return Hotel("Interactive Hotel")
    with open(DATA_FILE, "r", encoding="utf-8") as f: return Hotel.from_dict(json.load(f))

def save_hotel(h: Hotel) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(h.to_dict(), f, ensure_ascii=False, indent=2)

def run():
    h = load_hotel()
    print(f"Loaded from {DATA_FILE} (if existed).")
    while True:
        print_menu()
        c = input("Choose: ").strip()
        try:
            if c == "1":
                r = h.add_room(int(input("Room number: ")),
                               input("Room type: "),
                               float(input("Price per night: ")))
                save_hotel(h); print(f"Room {r.number} added.")
            elif c == "2":
                rs = h.list_rooms()
                if not rs: print("No rooms.")
                else:
                    for r in rs:
                        print(f"#{r.number} {r.room_type} {r.price_per_night} {r.status.value} occupied={r.is_occupied}")
            elif c == "3":
                g = h.register_guest(input("Guest name: "), input("Contact: "))
                save_hotel(h); print(f"Guest ID={g.guest_id}")
            elif c == "4":
                gs = h.list_guests()
                if not gs: print("No guests.")
                else:
                    for g in gs: print(f"ID={g.guest_id} {g.name} {g.contact}")
            elif c == "5":
                gid = int(input("Guest ID: "))
                rn = int(input("Room number: "))
                ci = parse_date(input("Check-in (YYYY-MM-DD): "))
                co = parse_date(input("Check-out (YYYY-MM-DD): "))
                b = h.create_booking(gid, rn, ci, co)
                save_hotel(h); print(f"Booking ID={b.id} status={b.status.value}")
            elif c == "6":
                bs = h.list_bookings()
                if not bs: print("No bookings.")
                else:
                    for b in bs:
                        print(f"ID={b.id} guest={b.guest.name} room={b.room.number} "
                              f"{b.check_in_date}->{b.check_out_date} status={b.status.value}")
            elif c == "7":
                h.cancel_booking(int(input("Booking ID: ")))
                save_hotel(h); print("Booking canceled.")
            elif c == "8":
                bid = int(input("Booking ID: "))
                h.check_in(bid, parse_date(input("Current date (YYYY-MM-DD): ")))
                save_hotel(h); print("Check-in OK.")
            elif c == "9":
                bid = int(input("Booking ID: "))
                total = h.check_out(bid, parse_date(input("Current date (YYYY-MM-DD): ")))
                save_hotel(h); print(f"Check-out OK. Total={total}")
            elif c == "10":
                h.delete_room(int(input("Room number: ")))
                save_hotel(h); print("Room deleted.")
            elif c == "11":
                h.delete_guest(int(input("Guest ID: ")))
                save_hotel(h); print("Guest deleted.")
            elif c == "0":
                save_hotel(h); print("Exit."); break
            else:
                print("Unknown menu item.")
        except (ValueError, RoomNotFoundError, GuestNotFoundError) as e:
            print("Error:", e)
        except Exception as e:
            print("Unexpected error:", e)

if __name__ == "__main__":
    run()
