// Maps a tool's `panel` name to the component shown in the right options panel,
// and (for full-width tools) the component shown in the center instead of the viewer.
import { ComponentType } from "react";
import { CropPanel, FormPanel, MetadataPanel, ViewPanel } from "./basic";
import { EditTextPanel, ImagesPanel, LinksPanel } from "./edit";
import { AnnotatePanel, CompareCenter, SharePanel } from "./review";
import { DigitalPanel, FormsPanel, SendPanel, SignPanel } from "./forms";
import { RedactPanel } from "./protect";
import { AiPanel, BatchCenter, MeasurePanel } from "./automate";
import { Organizer } from "./organize";

export const PANELS: Record<string, ComponentType> = {
  form: FormPanel,
  view: ViewPanel,
  metadata: MetadataPanel,
  crop: CropPanel,
  "edit-text": EditTextPanel,
  images: ImagesPanel,
  links: LinksPanel,
  annotate: AnnotatePanel,
  share: SharePanel,
  forms: FormsPanel,
  sign: SignPanel,
  digital: DigitalPanel,
  send: SendPanel,
  redact: RedactPanel,
  measure: MeasurePanel,
  ai: AiPanel,
};

export const CENTER_PANELS: Record<string, ComponentType> = {
  organize: Organizer,
  compare: CompareCenter,
  batch: BatchCenter,
};
