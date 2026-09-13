export type MoverDefault = "8" | "all";
export type AppNotification = { id: number; tone: "success" | "error"; message: string };
export type AppSettings = {
  theme: "light" | "dark";
  moverDefault: MoverDefault;
  density: "comfortable" | "compact";
  featureColor: boolean;
};
export type HelpItem = { term: string; detail: string };
