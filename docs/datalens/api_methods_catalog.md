# DataLens API Methods Catalog

Source trace: external docs corpus `raw/api/openapi.json`, `api_inventory.json`, and normalized method pages.

- OpenAPI version: `3.1.0`.
- RPC operation count: `88`.
- RPC path count: `88`.
- Required API header version: `2`.
- Lock SHA-256: `e4c3cf56de894e28b883b1f0ceaf2935f68570b052c46885e20bc9608e5ca532`.
- Support counts: `EXECUTABLE_TOOL_SUPPORTED`=38, `PLAN_ONLY_SUPPORTED`=18, `READ_ONLY_REFERENCE`=22, `UNSUPPORTED_NO_VALIDATED_METHOD`=10.

| Method | Tag | Mode | Support status | MCP tool/route | Request schema | Response schema |
| --- | --- | --- | --- | --- | --- | --- |
| `assignLicenses` | Licensing | `unsupported` | `UNSUPPORTED_NO_VALIDATED_METHOD` | unsupported | `AssignLicensesArgs` | `AssignLicensesResponse` |
| `batchListMembers` | Access | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `AccessExtBatchListMembersArgs` | `AccessExtBatchListMembersResult` |
| `cancelWorkbookExport` | WorkbookExport | `unsupported` | `UNSUPPORTED_NO_VALIDATED_METHOD` | unsupported | `CancelWorkbookExportArgs` | `CancelWorkbookExportResult` |
| `createCollection` | Collection | `unsupported` | `UNSUPPORTED_NO_VALIDATED_METHOD` | unsupported | `CreateCollectionArgs` | `CreateCollectionResult` |
| `createConnection` | Connection | `guarded_write` | `PLAN_ONLY_SUPPORTED` | dl_create_connector_plan | `ConnectionCreate` | `CreateConnectionResult` |
| `createDashboard` | Dashboard | `guarded_write` | `PLAN_ONLY_SUPPORTED` | dl_create_dashboard_plan | `CreateDashboardV1Args` | `CreateDashboardResponse` |
| `createDataset` | Dataset | `guarded_write` | `PLAN_ONLY_SUPPORTED` | dl_create_dataset_plan | `DatasetCreate` | `DatasetRead` |
| `createEditorChart` | Editor | `guarded_write` | `PLAN_ONLY_SUPPORTED` | dl_create_editor_chart_plan | `CreateEditorChartArgs` | `CreateEditorChartResult` |
| `createEmbed` | Embeds | `unsupported` | `UNSUPPORTED_NO_VALIDATED_METHOD` | unsupported | `CreateEmbedArgs` | `Embed` |
| `createEmbeddingSecret` | EmbeddingSecrets | `unsupported` | `UNSUPPORTED_NO_VALIDATED_METHOD` | unsupported | `CreateEmbeddingSecretArgs` | `CreateEmbeddingSecretResult` |
| `createFolder` | Folder | `unsupported` | `UNSUPPORTED_NO_VALIDATED_METHOD` | unsupported | `CreateFolderArgs` | `CreateFolderResult` |
| `createQLChart` | QL | `guarded_write` | `PLAN_ONLY_SUPPORTED` | dl_plan_object_create | `CreateQLChartArgs` | `CreateQLChartResponse` |
| `createReport` | Reports | `unsupported` | `UNSUPPORTED_NO_VALIDATED_METHOD` | unsupported | `CreateReportV1Args` | `CreateReportV1Result` |
| `createWizardChart` | Wizard | `guarded_write` | `PLAN_ONLY_SUPPORTED` | dl_create_wizard_chart_plan | `CreateWizardChartArgs` | `CreateWizardChartResponse` |
| `createWorkbook` | Workbook | `guarded_write` | `PLAN_ONLY_SUPPORTED` | guarded_write | `CreateWorkbookArgs` | `CreateWorkbookResult` |
| `deleteCollection` | Collection | `forbidden` | `READ_ONLY_REFERENCE` | forbidden | `DeleteCollectionArgs` | `DeleteCollectionResult` |
| `deleteCollections` | Collection | `forbidden` | `READ_ONLY_REFERENCE` | forbidden | `DeleteCollectionsArgs` | `DeleteCollectionsResult` |
| `deleteConnection` | Connection | `forbidden` | `READ_ONLY_REFERENCE` | forbidden | `DeleteConnectionRequest` | `` |
| `deleteDashboard` | Dashboard | `forbidden` | `READ_ONLY_REFERENCE` | forbidden | `DeleteDashboardArgs` | `DeleteDashboardResponse` |
| `deleteDataset` | Dataset | `forbidden` | `READ_ONLY_REFERENCE` | forbidden | `DeleteDatasetRequest` | `` |
| `deleteEditorChart` | Editor | `forbidden` | `READ_ONLY_REFERENCE` | forbidden | `DeleteEditorChartArgs` | `DeleteEditorChartResponse` |
| `deleteEmbed` | Embeds | `forbidden` | `READ_ONLY_REFERENCE` | forbidden | `DeleteEmbedArgs` | `DeleteEmbedResult` |
| `deleteEmbeddingSecret` | EmbeddingSecrets | `forbidden` | `READ_ONLY_REFERENCE` | forbidden | `DeleteEmbeddingSecretArgs` | `DeleteEmbeddingSecretResult` |
| `deleteFolder` | Folder | `forbidden` | `READ_ONLY_REFERENCE` | forbidden | `DeleteFolderArgs` | `DeleteFolderResponse` |
| `deleteQLChart` | QL | `forbidden` | `READ_ONLY_REFERENCE` | forbidden | `DeleteQLChartArgs` | `DeleteQLChartResponse` |
| `deleteReport` | Reports | `forbidden` | `READ_ONLY_REFERENCE` | forbidden | `DeleteReportArgs` | `DeleteReportResponse` |
| `deleteWizardChart` | Wizard | `forbidden` | `READ_ONLY_REFERENCE` | forbidden | `DeleteWizardChartArgs` | `DeleteWizardChartResponse` |
| `deleteWorkbook` | Workbook | `forbidden` | `READ_ONLY_REFERENCE` | forbidden | `DeleteWorkbookArgs` | `Workbook` |
| `deleteWorkbooks` | Workbook | `forbidden` | `READ_ONLY_REFERENCE` | forbidden | `DeleteWorkbooksArgs` | `DeleteWorkbooksResponse` |
| `dlsSuggest` | Folder | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `DlsSuggestArgs` | `DlsSuggestResult` |
| `getAuditEntriesUpdates` | Audit | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `GetAuditEntriesUpdatesArgs` | `GetAuditEntriesUpdatesResult` |
| `getAuditEntryPermissionsForUser` | Audit | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `GetAuditEntryPermissionsForUserArgs` | `GetAuditEntryPermissionsForUserResult` |
| `getCollection` | Collection | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `GetCollectionArgs` | `GetCollectionResult` |
| `getCollectionBreadcrumbs` | Collection | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `GetCollectionBreadcrumbsArgs` | `GetCollectionBreadcrumbsResult` |
| `getCollectionContent` | Collection | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `GetStructureItemsArgs` | `GetStructureItemsResult` |
| `getCollectionsByIds` | Collection | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `GetCollectionsByIdsArgs` | `GetCollectionsByIdsResponse` |
| `getConnection` | Connection | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_get_connection / dl_read_object | `GetConnectionRequest` | `ConnectionRead` |
| `getDashboard` | Dashboard | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_get_dashboard / dl_read_object | `GetDashboardV1Args` | `GetDashboardV1Result` |
| `getDataset` | Dataset | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_get_dataset / dl_read_object | `GetDatasetRequest` | `DatasetRead` |
| `getEditorChart` | Editor | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_get_editor_chart / dl_read_object | `GetEditorChartArgs` | `GetEditorChartResult` |
| `getEmbeddingSecret` | EmbeddingSecrets | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `GetEmbeddingSecretArgs` | `EmbeddingSecret` |
| `getEntries` | Navigation | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `GetEntriesV2Args` | `GetEntriesV2Result` |
| `getEntriesPermissions` | Entries | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `GetEntriesPermissionsArgs` | `GetEntriesPermissionsResult` |
| `getEntriesRelations` | Entries | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_get_entries_relations / dl_list_related_objects | `GetEntriesRelationsArgs` | `GetEntriesRelationsResult` |
| `getLicenses` | Licensing | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `GetLicensesArgs` | `GetLicensesResult` |
| `getLicensesLimit` | Licensing | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `` | `LicenseLimits` |
| `getPermissions` | Folder | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `GetPermissionsArgs` | `GetPermissionsResult` |
| `getPermissionsBulk` | Permissions | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `GetPermissionsBulkArgs` | `GetPermissionsBulkResult` |
| `getQLChart` | QL | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_read_object | `GetQLChartArgs` | `` |
| `getReport` | Reports | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `GetReportV1Args` | `GetReportV1Result` |
| `getRootCollectionPermissions` | Collection | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `` | `GetRootCollectionPermissionsResult` |
| `getWizardChart` | Wizard | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_get_wizard_chart / dl_read_object | `GetWizardChartArgs` | `` |
| `getWorkbook` | Workbook | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_get_workbook_entries / dl_rpc_readonly | `GetWorkbookArgs` | `GetWorkbookResult` |
| `getWorkbookEntries` | Workbook | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_get_workbook_entries | `GetWorkbookEntriesArgs` | `GetWorkbookEntriesResult` |
| `getWorkbookExportResult` | WorkbookExport | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `GetWorkbookExportResultArgs` | `GetWorkbookExportResultResult` |
| `getWorkbookExportStatus` | WorkbookExport | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `GetWorkbookExportStatusArgs` | `GetWorkbookExportStatusResult` |
| `getWorkbookImportStatus` | WorkbookImport | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `GetWorkbookImportStatusArgs` | `GetWorkbookImportStatusResult` |
| `getWorkbooksByIds` | Workbook | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `GetWorkbooksByIdsArgs` | `GetWorkbooksByIdsResponse` |
| `getWorkbooksList` | Workbook | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_list_workbooks | `GetWorkbooksListArgs` | `GetWorkbooksListResult` |
| `listCollectionAccessBindings` | Collection | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `ListCollectionAccessBindingsArgs` | `ListIamAccessBindingsResult` |
| `listDirectory` | Navigation | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `ListDirectoryArgs` | `ListDirectoryResult` |
| `listEmbeddingSecrets` | EmbeddingSecrets | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `ListEmbeddingSecretsArgs` | `ListEmbeddingSecretsResponse` |
| `listEmbeds` | Embeds | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `ListEmbedsArgs` | `ListEmbedsResponse` |
| `listSharedEntryAccessBindings` | SharedEntry | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `ListSharedEntryAccessBindingsArgs` | `ListIamAccessBindingsResult` |
| `listWorkbookAccessBindings` | Workbook | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `ListWorkbookAccessBindingsArgs` | `ListIamAccessBindingsResult` |
| `modifyPermissions` | Folder | `forbidden` | `READ_ONLY_REFERENCE` | forbidden | `ModifyPermissionsArgs` | `ModifyPermissionsResult` |
| `moveCollection` | Collection | `forbidden` | `READ_ONLY_REFERENCE` | forbidden | `MoveCollectionArgs` | `Collection` |
| `moveCollections` | Collection | `forbidden` | `READ_ONLY_REFERENCE` | forbidden | `MoveCollectionsArgs` | `MoveCollectionsResponse` |
| `moveFolderEntry` | Folder | `forbidden` | `READ_ONLY_REFERENCE` | forbidden | `MoveEntryArgs` | `MoveEntryResult` |
| `moveWorkbook` | Workbook | `forbidden` | `READ_ONLY_REFERENCE` | forbidden | `MoveWorkbookArgs` | `Workbook` |
| `moveWorkbooks` | Workbook | `forbidden` | `READ_ONLY_REFERENCE` | forbidden | `MoveWorkbooksArgs` | `MoveWorkbooksResponse` |
| `renameEntry` | Entries | `forbidden` | `READ_ONLY_REFERENCE` | forbidden | `RenameEntryArgs` | `RenameEntryResult` |
| `setLicenseLimit` | Licensing | `forbidden` | `READ_ONLY_REFERENCE` | forbidden | `SetLicenseLimitArgs` | `LicenseLimits` |
| `startWorkbookExport` | WorkbookExport | `guarded_write` | `PLAN_ONLY_SUPPORTED` | guarded_write | `StartWorkbookExportArgs` | `StartWorkbookExportResult` |
| `startWorkbookImport` | WorkbookImport | `guarded_write` | `PLAN_ONLY_SUPPORTED` | guarded_write | `StartWorkbookImportArgs` | `StartWorkbookImportResult` |
| `updateCollection` | Collection | `unsupported` | `UNSUPPORTED_NO_VALIDATED_METHOD` | unsupported | `UpdateCollectionArgs` | `Collection` |
| `updateCollectionAccessBindings` | Collection | `guarded_write` | `PLAN_ONLY_SUPPORTED` | guarded_write | `UpdateCollectionAccessBindingsArgs` | `DatalensOperation` |
| `updateConnection` | Connection | `guarded_write` | `PLAN_ONLY_SUPPORTED` | dl_update_connector_plan | `UpdateConnectionRequest` | `` |
| `updateDashboard` | Dashboard | `guarded_write` | `PLAN_ONLY_SUPPORTED` | dl_update_dashboard_plan / dl_save_object_plan / dl_publish_object_plan | `UpdateDashboardV1Args` | `UpdateDashboardResponse` |
| `updateDataset` | Dataset | `guarded_write` | `PLAN_ONLY_SUPPORTED` | dl_update_dataset_plan | `UpdateDatasetRequest` | `DatasetRead` |
| `updateEditorChart` | Editor | `guarded_write` | `PLAN_ONLY_SUPPORTED` | dl_update_editor_chart_plan | `UpdateEditorChartArgs` | `UpdateEditorChartResult` |
| `updateEmbed` | Embeds | `unsupported` | `UNSUPPORTED_NO_VALIDATED_METHOD` | unsupported | `UpdateEmbedArgs` | `Embed` |
| `updateQLChart` | QL | `guarded_write` | `PLAN_ONLY_SUPPORTED` | dl_plan_object_update | `UpdateQLChartArgs` | `UpdateQLChartResponse` |
| `updateReport` | Reports | `unsupported` | `UNSUPPORTED_NO_VALIDATED_METHOD` | unsupported | `UpdateReportV1Args` | `UpdateReportV1Result` |
| `updateWizardChart` | Wizard | `guarded_write` | `PLAN_ONLY_SUPPORTED` | dl_update_wizard_chart_plan | `UpdateWizardChartArgs` | `UpdateWizardChartResponse` |
| `updateWorkbook` | Workbook | `guarded_write` | `PLAN_ONLY_SUPPORTED` | guarded_write | `UpdateWorkbookArgs` | `Workbook` |
| `updateWorkbookAccessBindings` | Workbook | `guarded_write` | `PLAN_ONLY_SUPPORTED` | guarded_write | `UpdateWorkbookAccessBindingsArgs` | `DatalensOperation` |
| `validateDataset` | Dataset | `readonly` | `EXECUTABLE_TOOL_SUPPORTED` | dl_rpc_readonly | `ValidateDatasetRequest` | `DatasetRead` |
