import '@lab/corpus/Fingerprint.css';

/** How many decimals a measure is shown to. A count is whole; the one measure
 *  that is not -- how far a round primitive's axis leans out of its own plane
 *  -- is worth a fraction of a degree, because most parts carry a little
 *  authoring noise and the parts that matter carry degrees. */
function places(name: string) {
  return name.endsWith('-deg') ? 2 : 0;
}

/** What a part is built from, as `part_features` records it.
 *
 *  A feature with a null value is a flag -- it is either there or it is not,
 *  and only the ones that are there are drawn. A feature with a number is a
 *  measure, and every part has all of them. That null is the whole test, so
 *  this file never names a feature and cannot drift from the extractor's
 *  vocabulary the way a second list here would.
 *
 *  Optional for the same reason `tags` is: the lab's server is long-lived and
 *  can be older than the page in front of it. */
export function Fingerprint({ features }: {
  features?: Record<string, number | null>;
}) {
  if (!features) return null;
  const entries = Object.entries(features);
  const flags = entries.filter(([, value]) => value === null).map(([name]) => name);
  const measures = entries.filter(([, value]) => value !== null) as [string, number][];
  if (flags.length === 0 && measures.length === 0) return null;
  return (
    <div className="corpus-built">
      {flags.length > 0 && (
        <ul className="corpus-built-flags">
          {flags.map((name) => (
            <li key={name} className="corpus-built-flag" data-feature={name}>{name}</li>
          ))}
        </ul>
      )}
      {measures.length > 0 && (
        <dl className="corpus-built-measures">
          {measures.map(([name, value]) => (
            <div key={name} className="corpus-built-measure">
              <dt>{name}</dt>
              <dd>{value.toFixed(places(name))}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
