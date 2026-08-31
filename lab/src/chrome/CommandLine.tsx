import { useEffect, useState } from 'react';
import type { LabClient } from '@lab/api/client';

export interface CommandLineProps {
  client: LabClient;
  part: string;
  config: Record<string, unknown>;
}

/** The CLI command this trial is equivalent to, collapsed to the part id.
 *
 * The argv comes from the server, which builds it with the same function the
 * render uses. Building it here instead would be a second answer to what a
 * flag means.
 *
 * Only the part shows: at the lab's defaults the argv is twenty flags and
 * wraps the status bar to three lines. Hover opens the rest; a click pins it,
 * because a touch screen never hovers and the copy button has to be reachable.
 */
export function CommandLine({ client, part, config }: CommandLineProps) {
  const [command, setCommand] = useState('');
  const [hovered, setHovered] = useState(false);
  const [pinned, setPinned] = useState(false);
  const signature = `${part} ${JSON.stringify(config)}`;

  useEffect(() => {
    if (!part.trim()) {
      setCommand('');
      return;
    }
    let live = true;
    client.command(part, config).then((got) => {
      if (live) setCommand(got.command);
    }).catch(() => { if (live) setCommand(''); });
    return () => { live = false; };
  }, [signature]);

  if (!part.trim()) return <code className="command-line">no part chosen</code>;

  const open = (hovered || pinned) && command !== '';

  return (
    <span
      className="command"
      onPointerEnter={() => setHovered(true)}
      onPointerLeave={() => setHovered(false)}
      onKeyDown={(e) => { if (e.key === 'Escape') setPinned(false); }}
    >
      <code
        className="command-line"
        title={command}
        role="button"
        tabIndex={0}
        aria-expanded={open}
        onClick={() => setPinned((was) => !was)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') setPinned((was) => !was);
        }}
      >
        {part}
      </code>
      {open ? (
        <span className="command-callout">
          <code className="command-full">{command}</code>
          <button
            type="button"
            className="command-copy"
            onClick={() => { void navigator.clipboard?.writeText(command); }}
          >
            Copy
          </button>
        </span>
      ) : null}
    </span>
  );
}
