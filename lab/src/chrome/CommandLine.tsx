import { useEffect, useState } from 'react';
import type { LabClient } from '@lab/api/client';

export interface CommandLineProps {
  client: LabClient;
  part: string;
  config: Record<string, unknown>;
}

/** The CLI command this trial is equivalent to, always on screen.
 *
 * The argv comes from the server, which builds it with the same function the
 * render uses. Building it here instead would be a second answer to what a
 * flag means. */
export function CommandLine({ client, part, config }: CommandLineProps) {
  const [command, setCommand] = useState('');
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

  return (
    <code
      className="command-line"
      title="click to copy"
      role="button"
      tabIndex={0}
      onClick={() => navigator.clipboard?.writeText(command)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') navigator.clipboard?.writeText(command);
      }}
    >
      {command}
    </code>
  );
}
