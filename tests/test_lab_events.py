"""The lab's event stream: what a published change looks like on the wire."""
import asyncio

from brick_icons.lab import events


def test_a_subscriber_hears_each_publish_once():
    broker = events.Broker()
    heard = []
    stop = broker.subscribe(lambda kind, data: heard.append((kind, data)))
    broker.publish("changed", {"part": "3001"})
    stop()
    broker.publish("changed", {"part": "3002"})
    assert heard == [("changed", {"part": "3001"})]


def test_one_bad_subscriber_does_not_silence_the_rest():
    broker = events.Broker()
    heard = []
    broker.subscribe(lambda kind, data: 1 / 0)
    broker.subscribe(lambda kind, data: heard.append(data))
    broker.publish("changed", {"part": "3001"})
    assert heard == [{"part": "3001"}]


def test_an_event_is_framed_as_sse():
    assert events.frame("changed", {"sha": "ab", "part": "3001"}) == \
        'event: changed\ndata: {"part": "3001", "sha": "ab"}\n\n'


def test_the_stream_says_hello_then_carries_a_publish():
    broker = events.Broker()

    async def run():
        async def connected():
            return False
        stream = events.stream(broker, connected)
        first = await stream.__anext__()
        asyncio.get_running_loop().call_later(
            0.05, broker.publish, "changed", {"part": "3001"})
        second = await stream.__anext__()
        await stream.aclose()
        return first, second

    first, second = asyncio.run(run())
    assert first == ": connected\n\n"
    assert second == events.frame("changed", {"part": "3001"})


def test_a_closed_stream_stops_listening():
    broker = events.Broker()

    async def run():
        async def connected():
            return False
        stream = events.stream(broker, connected)
        await stream.__anext__()
        assert broker.listeners() == 1
        await stream.aclose()

    asyncio.run(run())
    assert broker.listeners() == 0
