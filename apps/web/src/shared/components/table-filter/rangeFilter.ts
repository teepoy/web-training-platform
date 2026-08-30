export interface NumericRangeFilterDescriptor {
  kind: "number";
  bounds: { min: number; max: number } | null;
  /** Slider increment only. Exact inputs remain unconstrained. */
  step: number;
  /** Slider tooltip precision only. Exact inputs preserve manually entered values. */
  displayPrecision: number;
}

export interface DateTimeRangeFilterDescriptor {
  kind: "datetime";
  /** The consumer opts into browser-local display explicitly; locale never selects a timezone. */
  timeZone: "browser";
  /** Describes transport semantics. The picker never changes the selected end boundary. */
  interval: "[start,end)" | "[start,end]";
}

export type RangeFilterDescriptor = NumericRangeFilterDescriptor | DateTimeRangeFilterDescriptor;
