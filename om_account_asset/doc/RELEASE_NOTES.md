## Module <om_account_asset>

#### 13.10.2026
#### Version 15.0.7.0.0
##### IMP
- sell or dispose of an asset: a wizard books the disposal entry with the gain or the loss, a fully
  depreciated asset can be disposed of too
##### FIX
- the assets of the bills posted by the auto-post job are created
- an asset is closed when its last depreciation entry is posted
- the asset tests no longer load files that are not shipped

#### 06.09.2022
#### Version 15.0.6.9.0
##### FIX
- prevent asset creation if Invoice/Bill is refund.

#### 29.04.2022
#### Version 15.0.6.7.0
##### FIX
- asset creation error from JE

#### 15.04.2022
#### Version 15.0.6.6.0
##### IMP
- turkish translation

#### 28.02.2022
#### Version 15.0.6.5.0
##### IMP
- remove deprecated method

#### 18.02.2022
#### Version 15.0.6.4.1
##### FIX
- Fix asset singleton

#### 28.01.2022
#### Version 15.0.6.4.0
##### FIX
- Fix Modify Depreciation wizard so final depreciation not deleted

#### 03.01.2022
#### Version 15.0.6.3.0
##### FIX
- remove logger warning: digits

#### 02.01.2022
#### Version 15.0.6.2.0
##### FIX
- assets

#### 31.12.2021
#### Version 15.0.6.1.0
##### FIX
-validation error on resetting to draft for validated assets


#### 31.12.2021
#### Version 15.0.6.0.0
##### FIX
-asset duplicate creation on reset to draft, float to monetory,
 multi currency update


#### 24.12.2021
#### Version 15.0.5.0.0
##### FIX
- asset

#### 21.12.2021
#### Version 15.0.4.0.0
##### FIX
- relative delta non integer error

#### 17.12.2021
#### Version 15.0.3.0.0
##### FIX
- missing security

#### 07.12.2021
#### Version 15.0.2.0.0
##### FIX
- missing asset category id from po to bill


