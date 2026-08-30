import { mergeMessageCatalogs } from "./catalog";
import { coreMessageCatalog } from "@/app/i18n/catalogs/core";
import { sharedMessageCatalog } from "@/shared/i18n/messages";
import { adminMessageCatalog } from "@/features/admin/i18n/messages";
import { authMessageCatalog } from "@/features/auth/i18n/messages";
import { automationsMessageCatalog } from "@/features/automations/i18n/messages";
import { dashboardMessageCatalog } from "@/features/dashboard/i18n/messages";
import { datasetCollectionsMessageCatalog } from "@/features/dataset-collections/i18n/messages";
import { datasetsMessageCatalog } from "@/features/datasets/i18n/messages";
import { libraryMessageCatalog } from "@/features/library/i18n/messages";
import { modelsMessageCatalog } from "@/features/models/i18n/messages";
import { scMessageCatalog } from "@/features/sc/i18n/messages";
import { schedulesMessageCatalog } from "@/features/schedules/i18n/messages";
import { settingsMessageCatalog } from "@/features/settings/i18n/messages";
import { taskTrackerMessageCatalog } from "@/features/task_tracker/i18n/messages";
import { trainingMessageCatalog } from "@/features/training/i18n/messages";

export const messageCatalogs = [
  coreMessageCatalog,
  sharedMessageCatalog,
  adminMessageCatalog,
  authMessageCatalog,
  automationsMessageCatalog,
  dashboardMessageCatalog,
  datasetCollectionsMessageCatalog,
  datasetsMessageCatalog,
  libraryMessageCatalog,
  modelsMessageCatalog,
  scMessageCatalog,
  schedulesMessageCatalog,
  settingsMessageCatalog,
  taskTrackerMessageCatalog,
  trainingMessageCatalog,
] as const;

export const messages = mergeMessageCatalogs(messageCatalogs);
