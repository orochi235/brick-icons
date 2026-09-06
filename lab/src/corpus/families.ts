import { cleanCategory, NO_CATEGORY } from '@lab/corpus/facts';

/** The catch-all. A category nobody has placed lands here rather than
 *  vanishing, so the library growing a new one never costs the wall a part. */
export const OTHER_FAMILY = 'Everything else';

/** Families in the order the sidebar draws them: the subjects first, then the
 *  two that are not a subject at all. */
export const FAMILIES = [
  'Bricks & plates',
  'Figures & accessories',
  'Technic & mechanism',
  'Electric & power',
  'Vehicles',
  'Openings & scenery',
  'Decoration',
  'Other themes',
  OTHER_FAMILY,
  'Not a part',
] as const;

export type Family = typeof FAMILIES[number];

const MEMBERS: Record<Exclude<Family, typeof OTHER_FAMILY>, string[]> = {
  'Bricks & plates': [
    'Brick', 'Plate', 'Tile', 'Slope', 'Wedge', 'Arch', 'Baseplate', 'Panel',
    'Bracket', 'Cylinder', 'Cone', 'Dish', 'Dome', 'Hemisphere', 'Sphere',
    'Block', 'Roof', 'Support', 'Bar', 'Platform',
  ],
  'Figures & accessories': [
    'Minifig', 'Figure', 'Maxifig', 'Bigfig', 'Microfig', 'Animal', 'Plant',
    'Bone', 'Cocoon', 'Tree', 'Flower', 'Horn', 'Bracelet', 'Tassel', 'Strap',
    'Umbrella', 'Brush', 'Tool', 'Claw', 'Net', 'Shell', 'Flame', 'Projectile',
  ],
  'Technic & mechanism': [
    'Technic', 'Axle', 'Turntable', 'Hinge', 'Spring', 'Screw', 'Pin', 'Rack',
    'Winch', 'Crank', 'Pneumatic', 'Hose', 'Magnet', 'String', 'Rope',
    'Rubber', 'Arm', 'Jack', 'Roller', 'Hook', 'Ring', 'Handle', 'Holder',
    'Ripcord', 'Pullback', 'Spinner', 'Winding', 'Trigger', 'Slide',
    'Conveyor', 'Turbine', 'Ball',
  ],
  'Electric & power': [
    'Electric', 'Motor', 'Battery', 'Light', 'LED', 'Cable', 'Power', 'Antenna',
  ],
  'Vehicles': [
    'Train', 'Car', 'Boat', 'Plane', 'Wheel', 'Wheels', 'Tyre', 'Bike',
    'Motorcycle', 'Tricycle', 'Monorail', 'Trailer', 'Crane', 'Excavator',
    'Forklift', 'Tractor', 'Tipper', 'Vehicle', 'Cockpit', 'Windscreen',
    'Sunroof', 'Sail', 'Propeller', 'Landing', 'Jet', 'Exhaust', 'Caterpillar',
    'Tow', 'Wheelbarrow', 'Bucket', 'Wing', 'Tail',
  ],
  'Openings & scenery': [
    'Door', 'Window', 'Glass', 'Fence', 'Gate', 'Garage', 'Staircase',
    'Ladder', 'Roadsign', 'Signpost', 'Lamppost', 'Rock', 'Container', 'Tap',
  ],
  'Decoration': [
    'Sticker', 'Flag', 'Sheet', 'Cardboard', 'Decoration', 'Cutout', 'Sprue',
  ],
  'Other themes': [
    'Duplo', 'Quatro', 'Fabuland', 'Scala', 'Belville', 'Friends', 'Clikits',
    'Znap', 'Modulex', 'Mursten', 'Homemaker', 'Constraction', 'Sports',
  ],
  'Not a part': ['Moved', 'Obsolete', NO_CATEGORY],
};

const BY_CATEGORY: Map<string, Family> = new Map();
for (const family of Object.keys(MEMBERS) as Exclude<Family, typeof OTHER_FAMILY>[]) {
  for (const name of MEMBERS[family]) BY_CATEGORY.set(name.toLowerCase(), family);
}

/** The family a clean category is drawn under. Case-folded, because the
 *  library spells the same category both ways across files. */
export function familyOf(category: string): Family {
  return BY_CATEGORY.get(category.toLowerCase()) ?? OTHER_FAMILY;
}

export interface FamilyFacet {
  family: Family;
  total: number;
  /** Members present in this slot, biggest first. */
  members: { name: string; n: number }[];
}

/** Category counts folded into the family rows the sidebar draws. A family
 *  with nothing in this slot is left out entirely -- an empty disclosure is a
 *  row that can only disappoint. */
export function familyFacets(counts: Map<string, number>): FamilyFacet[] {
  const byFamily = new Map<Family, { name: string; n: number }[]>();
  for (const [raw, n] of counts) {
    const name = cleanCategory(raw);
    const family = familyOf(name);
    const bucket = byFamily.get(family);
    if (bucket) bucket.push({ name, n });
    else byFamily.set(family, [{ name, n }]);
  }
  const out: FamilyFacet[] = [];
  for (const family of FAMILIES) {
    const members = byFamily.get(family);
    if (!members) continue;
    members.sort((a, b) => b.n - a.n || a.name.localeCompare(b.name));
    out.push({ family, total: members.reduce((sum, m) => sum + m.n, 0), members });
  }
  return out;
}
