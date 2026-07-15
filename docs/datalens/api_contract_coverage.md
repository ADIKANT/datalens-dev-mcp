# DataLens API Contract Coverage

This file is a distilled operation policy generated from the current OpenAPI catalog and compiled schema bundle.

## Source

- OpenAPI SHA-256: `e4c3cf56de894e28b883b1f0ceaf2935f68570b052c46885e20bc9608e5ca532`.
- Operations: `88`.
- Paths: `88`.
- Generated at: `2026-07-13T13:34:50.491355Z`.

## Status Counts

- `guarded_plan_only`: `18`
- `readonly_reference`: `22`
- `supported_tool`: `38`
- `unsupported_explicit`: `10`

## Operation Matrix

| Operation | Path | Status | Owner | Request closure hash | Response closure hash |
| --- | --- | --- | --- | --- | --- |
| `assignLicenses` | `/rpc/assignLicenses` | `unsupported_explicit` | explicit_unavailable_method_spec | `8ce46bc0f015e15986538176f9a822228817e63044c178735c04e76bb0831f7d` | `43ca6362cf6a66cbf7e3f2a04534f1b8b7ae7501a5f86d73f246c0c6c09d2a7f` |
| `batchListMembers` | `/rpc/batchListMembers` | `supported_tool` | dl_rpc_readonly | `a687fecd09659ca5ddc95870c4b1b0b0701ed4552aad71b885f9385bcb9a5b98` | `95b58d3e9b32157a58708395b2640c3de65f6abd1412b7a00e4a3401a5c9ee0f` |
| `cancelWorkbookExport` | `/rpc/cancelWorkbookExport` | `unsupported_explicit` | explicit_unavailable_method_spec | `b27f92fe87e581013423ebf8b935170476ff82893a92172c63e2ca56be419b4a` | `59f2b8abea04a03ade42cedc533bde9da121cbfd8f07b774340c277bbec5dd04` |
| `createCollection` | `/rpc/createCollection` | `unsupported_explicit` | explicit_unavailable_method_spec | `3de63579eb574eaffc381e22f229a602bf4e7f2dfb1d8e75fd80d945b4e9630f` | `a23aa97f0c94246f4599c137a8185b8ae1b76b1b68b4d389b8b4514ba679a291` |
| `createConnection` | `/rpc/createConnection` | `guarded_plan_only` | dl_create_connector_plan | `f00ea5f44cad700354cd48305c10be06d547d014714f58f8585258fb6a4f031c` | `23237edbb53eb5e4cba1d9e056ec5d20d41b6ce7fd1b1e342cb6745faceaa175` |
| `createDashboard` | `/rpc/createDashboard` | `guarded_plan_only` | dl_create_dashboard_plan | `d1d05732e6a5b393496406047088fa2366e95a3e367e0e3bd4a0d16cedc1a49c` | `cd78c33a3ce02d45fc1f662921b6353f96317774fea8e9d648f7d5bef06ff842` |
| `createDataset` | `/rpc/createDataset` | `guarded_plan_only` | dl_create_dataset_plan | `cc13a4e67fb050b4664b3c7e315f5f31e6b691af53088e36d57986a90476f85c` | `074b59554719efca09ff907575a2b590ea5628a86f39ce6f7968aee6a59ace9d` |
| `createEditorChart` | `/rpc/createEditorChart` | `guarded_plan_only` | dl_create_editor_chart_plan | `47159f8a05ba6fdff651d83c89199e730792dbdf5376e757d43d5f076ead1ad5` | `2e099a2d95c1dac94eb70bb2734d8e0227f4291d5cc0817a74329abf7f9cd3ae` |
| `createEmbed` | `/rpc/createEmbed` | `unsupported_explicit` | explicit_unavailable_method_spec | `60083bdd25b2b100908e059120433c3897418c1c38a4c2db827fe8de03605047` | `308e3b50ff12e04775d2dd7ce56162ecb2c56b9492422f012b4cefb95138a7b4` |
| `createEmbeddingSecret` | `/rpc/createEmbeddingSecret` | `unsupported_explicit` | explicit_unavailable_method_spec | `aff34b42942803686e1feb6985dcedd2f33f7e12b1d0a8f5314c4aeb22302f0e` | `8c1ed9a29939790a9d39aacfdd603f64bc9238c25a8fc91c3fafdc14b1a9eb86` |
| `createFolder` | `/rpc/createFolder` | `unsupported_explicit` | explicit_unavailable_method_spec | `e382f941dc42951b0324ba571838044cea5cbe7959992706e0a715dbfaf85be8` | `c9ec77747528293301175a7a9a545c8d12f312028582e99fdbaa4bdd4b52ccc2` |
| `createQLChart` | `/rpc/createQLChart` | `guarded_plan_only` | dl_plan_object_create | `631b20731473b5821dc21c5fd8588426e56956c415b8ccb81ebc50a953199dbd` | `93380b3dc561ef2ee237d7ac4e1123093a15682834838acb7951e92bd50556fb` |
| `createReport` | `/rpc/createReport` | `unsupported_explicit` | explicit_unavailable_method_spec | `d40515412fd29c9c0275df0e066a5868073d6f44f1154a2fbc2f90057a4e6870` | `fba2b9101acd03af1f9170613dea36c43d37394541cb23052621486110f4a6c4` |
| `createWizardChart` | `/rpc/createWizardChart` | `guarded_plan_only` | dl_create_wizard_chart_plan | `8fe7c5b65676aaee8f279666d93a62d818a0b183afedaf276b5bb9c5e696e197` | `1840c59fd6d8f2f8aa977863de318620dbf4a72ba23972f524829541a761ec83` |
| `createWorkbook` | `/rpc/createWorkbook` | `guarded_plan_only` | guarded_write | `5bb1cda29bd7df591e836b4e1e44b71dd1a8e8e6343446cc578f249be66fb3a0` | `cfbe555c35376be109ad4d24630ad70faebf5b001783f4a6c5d6b675bb11e86b` |
| `deleteCollection` | `/rpc/deleteCollection` | `readonly_reference` | dl_reference | `ca829841b4db4b3caaa165211fd8297b614981bcbbeb481e95fa353f1219df99` | `a5cdacd64ab8299e197e8121f28a19fa57428f486570b45976e479484879fbfb` |
| `deleteCollections` | `/rpc/deleteCollections` | `readonly_reference` | dl_reference | `b78ae61388be5b83e768b2fefb47211a33caa526f777a8a4f8ff2ee0fb080a2a` | `5ece711073c79c858e930680f4278df3df314ae681a8441a2903fc6bdc43648b` |
| `deleteConnection` | `/rpc/deleteConnection` | `readonly_reference` | dl_reference | `fe916be66751338ae5dff2aaf82b72bd4358f55116fec86eb83bca2fec17ad68` | `` |
| `deleteDashboard` | `/rpc/deleteDashboard` | `readonly_reference` | dl_reference | `596a00a6cb5a082fd613e82f4478706c48c573537f577152ab395dc9ad73f737` | `58511b0c6681fde88ecde318f0ea38c4ace73dd2745048daca982487423d1fe3` |
| `deleteDataset` | `/rpc/deleteDataset` | `readonly_reference` | dl_reference | `b48bbb96dfab0f22e75fa76f440c26a9a23ebc944625642f1e52b7e92ee335fb` | `` |
| `deleteEditorChart` | `/rpc/deleteEditorChart` | `readonly_reference` | dl_reference | `32148035690fdaa6e0fb765e3c42312a4ee4d24180f265e9ae4a73c1e62c8ecf` | `ef5e4867f6defbe921676f3de33fef3b30409e72a25c7a134554f0b803567648` |
| `deleteEmbed` | `/rpc/deleteEmbed` | `readonly_reference` | dl_reference | `6f272477c3642aac9046c7c4aa4de78e143f65b82e9ae403ded20f86cae1c7ce` | `84e5b241157f7ea65fd7a0358a680fb3e06a61fb6964c04e89758acf72c9c2ec` |
| `deleteEmbeddingSecret` | `/rpc/deleteEmbeddingSecret` | `readonly_reference` | dl_reference | `664b5eb02dee07d7aaaf4a3f8ba5241a58c47b083681639249dfb4a0b55e3c28` | `55e32aa3581dea3b60a7759c876f98e9362b001eb9e04eb9de1c3b0f03e1be5d` |
| `deleteFolder` | `/rpc/deleteFolder` | `readonly_reference` | dl_reference | `b1ab2c0285ae059e75f7a1cda7851fa03b87ae6a27994d50c66996b7fad10f5c` | `cf85fba833e3c498f428c5cf3061ac3d54cb93ed5d16d7b6ef20c82afc6b6aaf` |
| `deleteQLChart` | `/rpc/deleteQLChart` | `readonly_reference` | dl_reference | `635bb7c7da8505831d3cc25f49915c29ebafa1b07fcdc9bc685e0955d4d10460` | `09cc296064adb94bcdbede4bb4b52aa9d8631ceca9da6d0b89080ac6b5a96f9c` |
| `deleteReport` | `/rpc/deleteReport` | `readonly_reference` | dl_reference | `07f4c1a32a062a4eed93a2a43717defeb136f3f1aa15050dedb531ec6f907956` | `e43eca90d961333e573d6f844cce7cb40002e25030b337c94a8337523c4645dd` |
| `deleteWizardChart` | `/rpc/deleteWizardChart` | `readonly_reference` | dl_reference | `cc4a42dbb86c2c4886950aec4133930e7cbc57b6f3ef06ca8ffbedc43a5fcc71` | `c5431b6d5a26e6ab35fb8eed7b2412dde0d898d4339f26d68a721ac498eb32dd` |
| `deleteWorkbook` | `/rpc/deleteWorkbook` | `readonly_reference` | dl_reference | `0b3385643f6fade3c468d8020d72cb370ca300847269399bdd2249685720ea39` | `a085e8b69bc0dce61297fe2f38aa69a6d7abfd08d189104f48ac9931949a6c6b` |
| `deleteWorkbooks` | `/rpc/deleteWorkbooks` | `readonly_reference` | dl_reference | `3bce6b0682b3ee8d3c4e1d3a5d0bd04afc22ad36059ffb273e34c4d7b33d5f96` | `dd2386e66ac51f842ffabec45b4787a0990306b207cc88a4fa2cc58691e1c07c` |
| `dlsSuggest` | `/rpc/dlsSuggest` | `supported_tool` | dl_rpc_readonly | `e1875e5c862fc7ccdd60ac40c300668390f8339e9a7446e46aea51c702bfd229` | `8c05e7e937dea2a781a5b905d9ce83968fb4c29f53828cbd22b35e4127d28374` |
| `getAuditEntriesUpdates` | `/rpc/getAuditEntriesUpdates` | `supported_tool` | dl_rpc_readonly | `6b948da6f2fd07db171111ff61464e08847a70608dd6fcb73a3617f4bd06ad59` | `d3adda41f30b1a0f87298f515b75c0b89f5a69897774e73d86b21f6c699458f0` |
| `getAuditEntryPermissionsForUser` | `/rpc/getAuditEntryPermissionsForUser` | `supported_tool` | dl_rpc_readonly | `b440e64d349301287a053884b298b715d511f715e36d27c73d95a54eafdd5442` | `5a77f4a579bc68fd77020c2ed98ee61760054ce094675e9be40830cff79ea030` |
| `getCollection` | `/rpc/getCollection` | `supported_tool` | dl_rpc_readonly | `e6e96e7eb0cb4888605dd1e412ef144bee7bdbf29ecba1d9b1e382d82928c85e` | `097505e4b86f8e53239005b61c326b39b3a1bf840fbac8a83e823a7045ac4a88` |
| `getCollectionBreadcrumbs` | `/rpc/getCollectionBreadcrumbs` | `supported_tool` | dl_rpc_readonly | `8073e29191b2ca8dc7a4c6d127e3fff85e48f7705ceef426b2a91f24e3809d9c` | `b76efcb4a9b34ca0ff89b1ed0c7d2caedb44afd055415cf09a551e0050865c30` |
| `getCollectionContent` | `/rpc/getCollectionContent` | `supported_tool` | dl_rpc_readonly | `24a8c88e648cac1e3b3385a9c62ec12827abdc52224a79eef20072af120104df` | `1d71b7c07d5f96c5fa54b19244d842936e7becbb05319dec6070eefe4d6a1b41` |
| `getCollectionsByIds` | `/rpc/getCollectionsByIds` | `supported_tool` | dl_rpc_readonly | `a491160c1176e1641c8d566a173292903c7e2861c751fd9b4a5e484f8ea65d1e` | `46e3a1e97ae4536065ecc766fe2f2236d3516cdfca8382f3c7e5377fb114a76d` |
| `getConnection` | `/rpc/getConnection` | `supported_tool` | dl_get_connection / dl_read_object | `5d95335fe88ae17f6b669c46c32d411bb38bcb00589222319c0a65eb39926c87` | `81fa5bedd0799db0e50ebcb7bbf2a9999061b3bf06107f41604237496c1ba192` |
| `getDashboard` | `/rpc/getDashboard` | `supported_tool` | dl_get_dashboard / dl_read_object | `dd300d543885ab7b5a7eaf58fceaa9f822b173a1b2489448834898c566dca4b4` | `ab506a186c463597cdeb4a470b17bf1d3c1b69710502e6b75239bc734dc03910` |
| `getDataset` | `/rpc/getDataset` | `supported_tool` | dl_get_dataset / dl_read_object | `c529b38663c4a193371a3d82323b988ae2378e9e2d4f36fc9e6f33b181bb2e54` | `074b59554719efca09ff907575a2b590ea5628a86f39ce6f7968aee6a59ace9d` |
| `getEditorChart` | `/rpc/getEditorChart` | `supported_tool` | dl_get_editor_chart / dl_read_object | `caef685fbe10c59633ac444500bc10d971cf915b9e2634df496ff1fd6b8503d5` | `c63a1c1b3127b9e9d2c3033c53c813d0431bae0a256edd62179dc5b4321808e4` |
| `getEmbeddingSecret` | `/rpc/getEmbeddingSecret` | `supported_tool` | dl_rpc_readonly | `0a9677fd61f05f22065d03c4b0b85c4ad3a0440b6400db008c1a043bb9581f58` | `d58e4b78b863415146940586244df2b66454be4ea41d7e9af76a54e0dd711141` |
| `getEntries` | `/rpc/getEntries` | `supported_tool` | dl_rpc_readonly | `9c93d8620a2253d5328de06a27b56ffe94da807d3a02c08ef54d10245b99015e` | `43e5dafb68034513cff7c9d86ba6fa3953dadf437a337cff674937061284ba45` |
| `getEntriesPermissions` | `/rpc/getEntriesPermissions` | `supported_tool` | dl_rpc_readonly | `5a465326dc0cc83356b04640d8ae4b25246a2d0778b616d2234a85c3de0237c3` | `d5278fc531a0c4bcdae690607e84dced99988589d6b56b1c6d97f5ea2b9c37cd` |
| `getEntriesRelations` | `/rpc/getEntriesRelations` | `supported_tool` | dl_get_entries_relations / dl_list_related_objects | `1c6549444758c350507a01d512d0d3cd4287153c324712ea31fe79e6817882bd` | `fc4527e9ea2bb9cc9160a56dbdf88ea61f9916e4dd7b63bfcacd9591719736f2` |
| `getLicenses` | `/rpc/getLicenses` | `supported_tool` | dl_rpc_readonly | `82356a8c83cdbff2e9f3aab1447f16dff2529b9b41e74df69caafda07cb99b42` | `cffd4e1518939767831cdcadc7d899c254ef0887c9bb09ccda16cfc70e8a03b0` |
| `getLicensesLimit` | `/rpc/getLicensesLimit` | `supported_tool` | dl_rpc_readonly | `` | `874feab8781dcecd123130dadf5510a9253fc639365fac42d5e6e1fe38f15124` |
| `getPermissions` | `/rpc/getPermissions` | `supported_tool` | dl_rpc_readonly | `4613d030d73ee1d482ef88d19262824ce5bd96ab0d46fe4b0ad0ca9cc6d6651c` | `8d8419d72896a1faff27bcf154af43b38c279ef32c8ad5d20503c44a895230d9` |
| `getPermissionsBulk` | `/rpc/getPermissionsBulk` | `supported_tool` | dl_rpc_readonly | `8472daa3cac80cdebed0e0b935802a290cc8801a3a0f030fea8c67b4b9d3413f` | `9295317a0ec3332010056bf068d8660a59673f4a1c315ddf8defe1b17591acb2` |
| `getQLChart` | `/rpc/getQLChart` | `supported_tool` | dl_read_object | `2ef13669363ca50ccaeb48d1a484c48c02571e7397d0826fe70c4b85f89bc384` | `` |
| `getReport` | `/rpc/getReport` | `supported_tool` | dl_rpc_readonly | `c1aecc24a6e618ead91e1e962964af983135f38d79b8f4541557c0f223261c77` | `c9c994f86e1dbf305cc4d45ddffbfff21df177587b408b70191d659856e5f7dd` |
| `getRootCollectionPermissions` | `/rpc/getRootCollectionPermissions` | `supported_tool` | dl_rpc_readonly | `` | `fb580414f2fc6de23d196025bacf5c33dbf0a104798ed6a34ea201f666c52ff2` |
| `getWizardChart` | `/rpc/getWizardChart` | `supported_tool` | dl_get_wizard_chart / dl_read_object | `e28650e02aa1f0964c68f972ecd2a50492d9992eb65b840fa87fb73db359d5b5` | `` |
| `getWorkbook` | `/rpc/getWorkbook` | `supported_tool` | dl_get_workbook_entries / dl_rpc_readonly | `759886a443fc3438abbc38f6f8d540e9ba1b6e58ef1489295174ce91eb27a9c0` | `78da9dce8758a029577cb377de7d2678870595b0efab42b95fb90228196f1e2b` |
| `getWorkbookEntries` | `/rpc/getWorkbookEntries` | `supported_tool` | dl_get_workbook_entries | `899417a47f4c6910dd65c72b4143ff1c4780c4ae169057cd586e25b4b44897ac` | `4924c48a06fee8a3ea1d71ae20b4d49043e39c727721f1542454f3ff1710322d` |
| `getWorkbookExportResult` | `/rpc/getWorkbookExportResult` | `supported_tool` | dl_rpc_readonly | `2d960f7e345f212eb51a7756f4bce0148bfae2a6457e57b401421a17c93e7c11` | `c7452ab7cf897982fda4b546c0b19b90aa713fc6de821df77bc41720950bcecd` |
| `getWorkbookExportStatus` | `/rpc/getWorkbookExportStatus` | `supported_tool` | dl_rpc_readonly | `b3f88a16ab895af8258912f8ff3fd635a978c82bb80d8e144a54ca6d95f89f01` | `c9ce09de63536a928368d56c6aa0c99dc3d533251487e0059285bf64021459c1` |
| `getWorkbookImportStatus` | `/rpc/getWorkbookImportStatus` | `supported_tool` | dl_rpc_readonly | `9760f5f2d08734e91159b02400d0fc2176422904bab650ff79bba30e5f199a87` | `317c65c9842b8bae6e93defaeed5178a2145107befa7d94232018a83340ae411` |
| `getWorkbooksByIds` | `/rpc/getWorkbooksByIds` | `supported_tool` | dl_rpc_readonly | `71d5953e22e38648452a4d28fe26cd23711cd0ab7d4caf96143120c0ff7c3267` | `d8208707b0e925233ad4b4a5b3bbc88281ac82057b3d545e999743dd7cab9f66` |
| `getWorkbooksList` | `/rpc/getWorkbooksList` | `supported_tool` | dl_list_workbooks | `a194cd4a61543d59a093a73e5d5513923ded4e61a6fb1c440b0975ec8f43c368` | `8b8d31005119d356a8b8e9fb4a318f836a50de11e8567773757f510573ef2c1c` |
| `listCollectionAccessBindings` | `/rpc/listCollectionAccessBindings` | `supported_tool` | dl_rpc_readonly | `c0974081a758ae4e785814268629b10dc48e2d2f1b0fd64279f0b3e459dbeb34` | `ba8c373da0621f11f163ddad8e72f74aea5ec8a29941683e721aec9d9d51bfd2` |
| `listDirectory` | `/rpc/listDirectory` | `supported_tool` | dl_rpc_readonly | `1043a7646a52752a51e7faf91d6e313b95133fc974354e396a0715f67106f149` | `c840ccb42c3794f3991f3b51b990e04c27bfde489886cebe253da921423f908e` |
| `listEmbeddingSecrets` | `/rpc/listEmbeddingSecrets` | `supported_tool` | dl_rpc_readonly | `c784469f5d10856fab61debae2d1c8b4224adda9c2e7f649181b1bbd42ff3ea4` | `b7db4dd1d062b317bae544508e7756a3fed3341a4477877d87aa174bbb1afdfc` |
| `listEmbeds` | `/rpc/listEmbeds` | `supported_tool` | dl_rpc_readonly | `cff35f33857b9d7268b5256ed38c2eb58007d5f434cf23409fe2ffb02e380b33` | `65a03639f349c14af7bcfd22ff5f84996ac12e1d14f7688ae70fcca535ba9071` |
| `listSharedEntryAccessBindings` | `/rpc/listSharedEntryAccessBindings` | `supported_tool` | dl_rpc_readonly | `56413f533aec0bd25677304e12390c858e367d1328baa0fc969c446bca32358c` | `ba8c373da0621f11f163ddad8e72f74aea5ec8a29941683e721aec9d9d51bfd2` |
| `listWorkbookAccessBindings` | `/rpc/listWorkbookAccessBindings` | `supported_tool` | dl_rpc_readonly | `c0706e150241f8763d81d7fe946008b84488980f61ddcfcf704b77761fa0c65d` | `ba8c373da0621f11f163ddad8e72f74aea5ec8a29941683e721aec9d9d51bfd2` |
| `modifyPermissions` | `/rpc/modifyPermissions` | `readonly_reference` | dl_reference | `49f96bfa83c799cfe8210d9e0788ec7ed7a999eff063cded43fa7d43a0ae8b77` | `7f9ba4f118ef8f73ff9711e6af157335d7ef5db5820c8eec0ae63eeced85a2da` |
| `moveCollection` | `/rpc/moveCollection` | `readonly_reference` | dl_reference | `80c8160d6f2971367e9eea80101d82bbef6f3d867c8f2ff527b1ac99c9cec4af` | `e6ee120eb05c95751e8af2a2bbba2f8f658eeeca4e34c7f246df51cf3ff5e1f4` |
| `moveCollections` | `/rpc/moveCollections` | `readonly_reference` | dl_reference | `9f80109d1fad490438b97571d3f07c0ca74b03a3f14c3efa222b3e3ee47f17a6` | `23ada1fab4c2faba60ac861d02466059a3e00de7369737d1b33232d55cc0049b` |
| `moveFolderEntry` | `/rpc/moveFolderEntry` | `readonly_reference` | dl_reference | `046e36b26ab31c5946780d9644296352bcb9f376a7114ccdac1a8d40cf38bdc3` | `2182e1f6acb4c01e77b0d3a347dc2e3d6b42a31eaa741a511eb7620454f35ca6` |
| `moveWorkbook` | `/rpc/moveWorkbook` | `readonly_reference` | dl_reference | `aa576787ed83bf742f784c9dd78b47e033eec06b9b3d27ca368a4b2ff65f8ccc` | `a085e8b69bc0dce61297fe2f38aa69a6d7abfd08d189104f48ac9931949a6c6b` |
| `moveWorkbooks` | `/rpc/moveWorkbooks` | `readonly_reference` | dl_reference | `2446f218f473971c0a6863903f193c8be55fc4af7cb162da2da6d9d92e88c070` | `9d64dd88da00e7fd1ea6b9f16dd5b39caee8b4dfbc4f2f56ff38245c0f7871b3` |
| `renameEntry` | `/rpc/renameEntry` | `readonly_reference` | dl_reference | `2b02e4ec0fbb97673e24f692eb61aa7afb00de289bf7eda4e5dc74f6d15b0013` | `9e0e41fbcafa9b931ab57ba9221ddf083b6b26d6b5e08ce2e9a7b8a7596e20c6` |
| `setLicenseLimit` | `/rpc/setLicenseLimit` | `readonly_reference` | dl_reference | `4132310270a10170c32714e022e8b0d45a75f59d72e5db8b60026e0d1083a7bf` | `874feab8781dcecd123130dadf5510a9253fc639365fac42d5e6e1fe38f15124` |
| `startWorkbookExport` | `/rpc/startWorkbookExport` | `guarded_plan_only` | guarded_write | `ce8e85b25eabd1ce7f13daf17e4fc9fae047ad81bbd916ef242c4ff77a0177c7` | `f98db6ffe722fcc3ba02317d859b7c8d211e1b8bcbd82daeace0455340035ddd` |
| `startWorkbookImport` | `/rpc/startWorkbookImport` | `guarded_plan_only` | guarded_write | `5c2c835db954f3e48a38d970648e91baf09d0d994d9f571307db520fe6141995` | `ce297c998676383bba72f75aa7003022042b4604085967e8ed8a2c3628b39b1d` |
| `updateCollection` | `/rpc/updateCollection` | `unsupported_explicit` | explicit_unavailable_method_spec | `37cb2413638d2c802f27fd97605340be7f1ac54317922d905d9bbb2b6a39d3ee` | `e6ee120eb05c95751e8af2a2bbba2f8f658eeeca4e34c7f246df51cf3ff5e1f4` |
| `updateCollectionAccessBindings` | `/rpc/updateCollectionAccessBindings` | `guarded_plan_only` | guarded_write | `38c9ca2cd4ab1f790b7112ef0482e309abd652373896c87fa3cddd6ac2f40f17` | `2154e92d561d016f8bbf5990016532ccd97b0296d3675a654ad7b8f319da591b` |
| `updateConnection` | `/rpc/updateConnection` | `guarded_plan_only` | dl_update_connector_plan | `ca1db6c0de181b369ee99729d20d6debd5bad4cb432e265c76d19c0b94e15b14` | `` |
| `updateDashboard` | `/rpc/updateDashboard` | `guarded_plan_only` | dl_update_dashboard_plan / dl_save_object_plan / dl_publish_object_plan | `75fd0b3565d7a8d0481c874983e09a56f951809585511151dcc127c008ceb287` | `5b03631ca0bf09983d2bbcba15556d79942f72108a103ed6bb0b2e98bc9023f7` |
| `updateDataset` | `/rpc/updateDataset` | `guarded_plan_only` | dl_update_dataset_plan | `e0fc917142cfc5845f30f38960ee1cd5c057a5817de8fed93135ff7cc83faeeb` | `074b59554719efca09ff907575a2b590ea5628a86f39ce6f7968aee6a59ace9d` |
| `updateEditorChart` | `/rpc/updateEditorChart` | `guarded_plan_only` | dl_update_editor_chart_plan | `c9a3c250668ba2151f0734828b7524559918adb5588a925f7fa11ada6dd66dc2` | `39d7fd1af34881ab46e9d467dd530685da85ef1afbfcce096d0bebbc73334153` |
| `updateEmbed` | `/rpc/updateEmbed` | `unsupported_explicit` | explicit_unavailable_method_spec | `82ce0881cce3c6d79e7f9c8e9cbdf13f5a5615e249f0bce2d6064a99643af5db` | `308e3b50ff12e04775d2dd7ce56162ecb2c56b9492422f012b4cefb95138a7b4` |
| `updateQLChart` | `/rpc/updateQLChart` | `guarded_plan_only` | dl_plan_object_update | `82120796079a9290523166cf4ac931b6fb5440fd6f6aebb533b511b6e604b5ad` | `1794ec8024ee3dc85c2688e0f2215fdaa7058a3d959bff24d87ef51c58b200a4` |
| `updateReport` | `/rpc/updateReport` | `unsupported_explicit` | explicit_unavailable_method_spec | `0912edd8e40fe139fdcc28123f98fb80cec74a3ed222eec60be8b6bd0ac2edfa` | `8db5983ec1192b2238801bedf79107ddb2b1b7ddfffd25dbc395ce90e5570b39` |
| `updateWizardChart` | `/rpc/updateWizardChart` | `guarded_plan_only` | dl_update_wizard_chart_plan | `eeb2c04647ff1948405c19f69f312652e6bb51c1554fcd0a4c9dae9c8c4ce99f` | `2068e6f575aff6545220ad27f24f53ebfaf3b26d4e55405f2b894bcd202471f0` |
| `updateWorkbook` | `/rpc/updateWorkbook` | `guarded_plan_only` | guarded_write | `5445e8010ffafc91168f8f2bcca783ade001925a81d54438cd230e5f79d8d9b2` | `a085e8b69bc0dce61297fe2f38aa69a6d7abfd08d189104f48ac9931949a6c6b` |
| `updateWorkbookAccessBindings` | `/rpc/updateWorkbookAccessBindings` | `guarded_plan_only` | guarded_write | `98b2e532ad0eff614909dd0d478fc2c33ae9739eeb0305ebd7b0ae87b8edcdcc` | `2154e92d561d016f8bbf5990016532ccd97b0296d3675a654ad7b8f319da591b` |
| `validateDataset` | `/rpc/validateDataset` | `supported_tool` | dl_rpc_readonly | `6fb1be2583fd0fc84b1613d19da502375ee3a1a0b1da2e6eea1d6ec7a05eda46` | `074b59554719efca09ff907575a2b590ea5628a86f39ce6f7968aee6a59ace9d` |
