// Golden fixture only. Production generation replaces this tab with a caller-owned dataset binding.
module.exports = {
  rows: [
    {event: 'metadata', data: {names: ['resource_id', 'resource_name', 'item_id', 'start_at', 'end_at', 'status', 'owner', 'link']}},
    {event: 'row', data: ['room_a', 'Room A', 'booking_1', '2026-07-13T08:00:00Z', '2026-07-13T10:00:00Z', 'confirmed', 'Team A', 'https://example.test/bookings/1']},
    {event: 'row', data: ['room_a', 'Room A', 'booking_2', '2026-07-13T09:30:00Z', '2026-07-13T11:00:00Z', 'confirmed', 'Team B', '/bookings/2']},
    {event: 'row', data: ['room_b', 'Room B', 'booking_3', '2026-07-13T23:00:00+03:00', '2026-07-14T01:00:00+03:00', 'cancelled', 'Team C', 'javascript:alert(1)']},
  ],
};
