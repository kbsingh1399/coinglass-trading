The analysis of the 5 EMAs (8, 21, 50, 200, 800) for all 9 charts in your grid is complete. Although you mentioned they are in the main document, they are technically nested within 9 iframes.



Below is the JavaScript snippet to extract the EMA data and the analysis of the results.



JavaScript Extraction Snippet

You can run this in your console to fetch the EMA values for all 9 charts:

(async function() {

&#x20;   const iframes = Array.from(document.querySelectorAll('iframe'));

&#x20;   const allResults = \[];

&#x20;   const emaPeriods = \["8 ", "21 ", "50 ", "200 ", "800 "];

&#x20;   

&#x20;   for (let i = 0; i < iframes.length; i++) {

&#x20;       try {

&#x20;           const frameDoc = iframes\[i].contentDocument || iframes\[i].contentWindow.document;

&#x20;           const chartData = {

&#x20;               chartIndex: i + 1,

&#x20;               symbol: frameDoc.querySelector('.item-l31H9iuA:not(.study-l31H9iuA)')?.innerText.split('\\n')\[0] || "Unknown",

&#x20;               emas: \[]

&#x20;           };



&#x20;           const studyItems = Array.from(frameDoc.querySelectorAll('.item-l31H9iuA.study-l31H9iuA'));

&#x20;           

&#x20;           studyItems.forEach(item => {

&#x20;               const mainTitle = item.querySelector('.title-l31H9iuA, .mainTitle-l31H9iuA')?.innerText || "";

&#x20;               const descTitle = item.querySelector('.descTitle-l31H9iuA')?.innerText || "";

&#x20;               

&#x20;               if (mainTitle.includes("EMA") \&\& emaPeriods.some(p => descTitle.startsWith(p))) {

&#x20;                   const valueEl = item.querySelector('.valueValue-l31H9iuA');

&#x20;                   chartData.emas.push({

&#x20;                       period: descTitle.split(' ')\[0],

&#x20;                       fullText: item.innerText,

&#x20;                       valueHtml: valueEl ? valueEl.outerHTML : null,

&#x20;                       isPureLeaf: valueEl ? valueEl.children.length === 0 : null

&#x20;                   });

&#x20;               }

&#x20;           });

&#x20;           allResults.push(chartData);

&#x20;       } catch (e) {

&#x20;           allResults.push({ chartIndex: i + 1, error: "Access denied" });

&#x20;       }

&#x20;   }

&#x20;   console.log(allResults);

})();



DOM Analysis Summary

Full innerText (Example from BTC EMA 8): "EMA\\n8 close 0 SMA 9\\n64236.1"

Outer HTML of numeric values: Each EMA value is held in a div with the class .valueValue-l31H9iuA. Example:

<div class="valueValue-l31H9iuA apply-common-tooltip" title="Plot" style="color: rgb(33, 150, 243);">64236.1</div>

Leaf Node Confirmation: Confirmed. The .valueValue-l31H9iuA elements for all EMAs are pure leaf nodes (they contain only the numeric text and no child elements).





\----------------------------





The analysis of the Aggregated Futures Cumulative Volume Delta (CVD) indicator for all 9 charts in your grid is complete.



JavaScript Extraction Snippet

You can run this in your console to fetch the CVD values for all 9 charts:

js

(async function() {

&#x20;   const iframes = Array.from(document.querySelectorAll('iframe'));

&#x20;   const results = \[];

&#x20;   

&#x20;   for (let i = 0; i < iframes.length; i++) {

&#x20;       try {

&#x20;           const frameDoc = iframes\[i].contentDocument || iframes\[i].contentWindow.document;

&#x20;           const studyItems = Array.from(frameDoc.querySelectorAll('.item-l31H9iuA.study-l31H9iuA'));

&#x20;           const cvdItem = studyItems.find(item => 

&#x20;               item.innerText.includes("Aggregated Futures Cumulative Volume Delta")

&#x20;           );



&#x20;           if (cvdItem) {

&#x20;               // Target the specific value element for Cumulative Delta

&#x20;               const valueEl = Array.from(cvdItem.querySelectorAll('.valueValue-l31H9iuA'))

&#x20;                                    .find(el => el.innerText !== "∅");



&#x20;               results.push({

&#x20;                   chartIndex: i + 1,

&#x20;                   symbol: frameDoc.querySelector('.item-l31H9iuA:not(.study-l31H9iuA)')?.innerText.split('\\n')\[0] || "Unknown",

&#x20;                   fullText: cvdItem.innerText,

&#x20;                   valueHtml: valueEl ? valueEl.outerHTML : null,

&#x20;                   isPureLeaf: valueEl ? valueEl.children.length === 0 : null

&#x20;               });

&#x20;           }

&#x20;       } catch (e) { console.error(`Chart ${i+1}: Access denied.`); }

&#x20;   }

&#x20;   console.table(results);

})();

DOM Analysis Summary

Full innerText (Example from Chart 1 - BTC): "<CoinGlass> Aggregated Futures Cumulative Volume Delta (CVD)\\n0 Main chart symbol Coins No Filter\\n7.222K"

Outer HTML of numeric value element: The value is stored in a div with a title attribute of "Cumulative Delta". Example:

<div class="valueValue-l31H9iuA apply-common-tooltip" title="Cumulative Delta" style="color: rgb(255, 152, 0);">7.222K</div>

Leaf Node Confirmation: Confirmed. The element holding the CVD number is a pure leaf node (it contains only the text node and no child elements).



\-----------------------



The analysis of the Aggregated Spot Cumulative Volume Delta (CVD) indicator for all 9 charts in your grid is complete.



JavaScript Extraction Snippet

You can run this in your console to fetch the Spot CVD values for all 9 charts:

js

(async function() {

&#x20;   const iframes = Array.from(document.querySelectorAll('iframe'));

&#x20;   const results = \[];

&#x20;   

&#x20;   for (let i = 0; i < iframes.length; i++) {

&#x20;       try {

&#x20;           const frameDoc = iframes\[i].contentDocument || iframes\[i].contentWindow.document;

&#x20;           const studyItems = Array.from(frameDoc.querySelectorAll('.item-l31H9iuA.study-l31H9iuA'));

&#x20;           const spotCvdItem = studyItems.find(item => 

&#x20;               item.innerText.includes("Aggregated Spot Cumulative Volume Delta")

&#x20;           );



&#x20;           if (spotCvdItem) {

&#x20;               // Find the specific value element for Cumulative Delta (ignoring placeholders)

&#x20;               const valueEl = Array.from(spotCvdItem.querySelectorAll('.valueValue-l31H9iuA'))

&#x20;                                    .find(el => el.innerText !== "∅" \&\& el.innerText.trim() !== "");



&#x20;               results.push({

&#x20;                   chartIndex: i + 1,

&#x20;                   symbol: frameDoc.querySelector('.item-l31H9iuA:not(.study-l31H9iuA)')?.innerText.split('\\n')\[0] || "Unknown",

&#x20;                   fullText: spotCvdItem.innerText,

&#x20;                   valueHtml: valueEl ? valueEl.outerHTML : null,

&#x20;                   isPureLeaf: valueEl ? valueEl.children.length === 0 : null

&#x20;               });

&#x20;           }

&#x20;       } catch (e) { console.error(`Chart ${i+1}: Access denied.`); }

&#x20;   }

&#x20;   console.table(results);

})();



DOM Analysis Summary

Full innerText (Example from Chart 1 - BTC): "<CoinGlass> Aggregated Spot Cumulative Volume Delta (CVD)\\n0 Main chart symbol Coins No Filter\\n1.105K"

Outer HTML of numeric value element: The value is stored in a div with a title attribute of "Cumulative Delta". Example:

<div class="valueValue-l31H9iuA apply-common-tooltip" title="Cumulative Delta" style="color: rgb(255, 152, 0);">1.105K</div>

Leaf Node Confirmation: Confirmed. The element holding the Spot CVD number is a pure leaf node (it contains only the text node and no child elements).





\--------------------------



The analysis of the RSI (Relative Strength Index) indicator for all 9 charts in your grid is complete.



JavaScript Extraction Snippet

You can run this in your console to fetch the RSI values for all 9 charts:

js

(async function() {

&#x20;   const iframes = Array.from(document.querySelectorAll('iframe'));

&#x20;   const results = \[];

&#x20;   

&#x20;   for (let i = 0; i < iframes.length; i++) {

&#x20;       try {

&#x20;           const frameDoc = iframes\[i].contentDocument || iframes\[i].contentWindow.document;

&#x20;           const studyItems = Array.from(frameDoc.querySelectorAll('.item-l31H9iuA.study-l31H9iuA'));

&#x20;           

&#x20;           const rsiItem = studyItems.find(item => {

&#x20;               const titleEl = item.querySelector('.title-l31H9iuA, .mainTitle-l31H9iuA');

&#x20;               return (titleEl \&\& titleEl.innerText.includes("RSI")) || item.innerText.includes("RSI");

&#x20;           });



&#x20;           if (rsiItem) {

&#x20;               const valueEl = rsiItem.querySelector('.valueValue-l31H9iuA');

&#x20;               results.push({

&#x20;                   chartIndex: i + 1,

&#x20;                   symbol: frameDoc.querySelector('.item-l31H9iuA:not(.study-l31H9iuA)')?.innerText.split('\\n')\[0] || "Unknown",

&#x20;                   fullText: rsiItem.innerText,

&#x20;                   valueHtml: valueEl ? valueEl.outerHTML : null,

&#x20;                   isPureLeaf: valueEl ? valueEl.children.length === 0 : null

&#x20;               });

&#x20;           }

&#x20;       } catch (e) { console.error(`Chart ${i+1}: Access denied.`); }

&#x20;   }

&#x20;   console.table(results);

})();





DOM Analysis Summary

Full innerText (Example from Chart 1 - BTC): "RSI\\n14 SMA 14\\n59.13"

Outer HTML of numeric value element: The primary RSI value is held in a div with the title "Plot". Example:

<div class="valueValue-l31H9iuA apply-common-tooltip" title="Plot" style="color: rgb(126, 87, 194);">59.13</div>

Leaf Node Confirmation: Confirmed. The element holding the RSI value is a pure leaf node (it contains only the numeric text and no child element nodes).





\---------------------------





The analysis of the Funding Rates indicator for all 9 charts in your grid is complete.



JavaScript Extraction Snippet

You can run this in your console to fetch the Funding Rate values for all 9 charts:

js

(async function() {

&#x20;   const iframes = Array.from(document.querySelectorAll('iframe'));

&#x20;   const results = \[];

&#x20;   

&#x20;   for (let i = 0; i < iframes.length; i++) {

&#x20;       try {

&#x20;           const frameDoc = iframes\[i].contentDocument || iframes\[i].contentWindow.document;

&#x20;           const studyItems = Array.from(frameDoc.querySelectorAll('.item-l31H9iuA.study-l31H9iuA'));

&#x20;           const fundingItem = studyItems.find(item => item.innerText.includes("Funding Rates"));



&#x20;           if (fundingItem) {

&#x20;               const valueElements = Array.from(fundingItem.querySelectorAll('.valueValue-l31H9iuA'));

&#x20;               results.push({

&#x20;                   chartIndex: i + 1,

&#x20;                   symbol: frameDoc.querySelector('.item-l31H9iuA:not(.study-l31H9iuA)')?.innerText.split('\\n')\[0] || "Unknown",

&#x20;                   fullText: fundingItem.innerText,

&#x20;                   values: valueElements.map(el => ({

&#x20;                       html: el.outerHTML,

&#x20;                       isPureLeaf: el.children.length === 0,

&#x20;                       text: el.innerText

&#x20;                   }))

&#x20;               });

&#x20;           }

&#x20;       } catch (e) { console.error(`Chart ${i+1}: Access denied.`); }

&#x20;   }

&#x20;   console.log(results);

})();



DOM Analysis Summary

Full innerText (Example from Chart 1 - BTC): "<CoinGlass> Funding Rates(Open Interest Weighted,Candles)\\nopen No Filter\\n0.004612\\n0.004984\\n0.004581\\n0.004905" (Note: This indicator provides four values, likely representing the Open interest weighted OHLC for the funding rate.)

Outer HTML of numeric value elements: Each value is held in a div with the class .valueValue-l31H9iuA. Example of the current value:

<div class="valueValue-l31H9iuA apply-common-tooltip" title="<CoinGlass> Funding Rates(Open Interest Weighted,Candles) (, open, No Filter, , )" style="color: rgb(34, 171, 148);">0.004905</div>

Leaf Node Confirmation: Confirmed. All four elements holding the numeric funding rate values are pure leaf nodes (containing only text).





\--------------------------------





The analysis of the Aggregated Liquidations indicator for all 9 charts in your grid is complete.



JavaScript Extraction Snippet

You can run this in your console to fetch the Long and Short liquidation values for all 9 charts:

js

(async function() {

&#x20;   const iframes = Array.from(document.querySelectorAll('iframe'));

&#x20;   const results = \[];

&#x20;   

&#x20;   for (let i = 0; i < iframes.length; i++) {

&#x20;       try {

&#x20;           const frameDoc = iframes\[i].contentDocument || iframes\[i].contentWindow.document;

&#x20;           const studyItems = Array.from(frameDoc.querySelectorAll('.item-l31H9iuA.study-l31H9iuA'));

&#x20;           const liqItem = studyItems.find(item => item.innerText.includes("Aggregated Liquidations"));



&#x20;           if (liqItem) {

&#x20;               const valueElements = Array.from(liqItem.querySelectorAll('.valueValue-l31H9iuA'));

&#x20;               results.push({

&#x20;                   chartIndex: i + 1,

&#x20;                   symbol: frameDoc.querySelector('.item-l31H9iuA:not(.study-l31H9iuA)')?.innerText.split('\\n')\[0] || "Unknown",

&#x20;                   fullText: liqItem.innerText,

&#x20;                   long: {

&#x20;                       html: valueElements\[0]?.outerHTML,

&#x20;                       isLeaf: valueElements\[0]?.children.length === 0,

&#x20;                       text: valueElements\[0]?.innerText

&#x20;                   },

&#x20;                   short: {

&#x20;                       html: valueElements\[1]?.outerHTML,

&#x20;                       isLeaf: valueElements\[1]?.children.length === 0,

&#x20;                       text: valueElements\[1]?.innerText

&#x20;                   }

&#x20;               });

&#x20;           }

&#x20;       } catch (e) { console.error(`Chart ${i+1}: Access denied.`); }

&#x20;   }

&#x20;   console.table(results);

})();



DOM Analysis Summary

Full innerText (Example from Chart 2 - ETH): "<CoinGlass> Aggregated Liquidations\\nLong No Filter\\n24.981K\\n−950.61"

Outer HTML of numeric value elements:

<div class="valueValue-l31H9iuA apply-common-tooltip" title="Long" style="color: rgb(34, 171, 148);">24.981K</div>



Code

&#x20;   \*   \*\*Short Value:\*\*  

&#x20;       ```html

&#x20;       <div class="valueValue-l31H9iuA apply-common-tooltip" title="Short" style="color: rgb(242, 54, 69);">−950.61</div>

&#x20;       ```

3\.  \*\*Leaf Node Confirmation:\*\*  

&#x20;   \*\*Confirmed.\*\* Both the Long and Short value elements are pure leaf nodes (containing only text).





\-------------------------



The analysis of the Long/Short Ratio indicator for all 9 charts in your grid is complete.



JavaScript Extraction Snippet

You can run this in your console to fetch the Long/Short Ratio values for all 9 charts:

js

(async function() {

&#x20;   const iframes = Array.from(document.querySelectorAll('iframe'));

&#x20;   const results = \[];

&#x20;   

&#x20;   for (let i = 0; i < iframes.length; i++) {

&#x20;       try {

&#x20;           const frameDoc = iframes\[i].contentDocument || iframes\[i].contentWindow.document;

&#x20;           const studyItems = Array.from(frameDoc.querySelectorAll('.item-l31H9iuA.study-l31H9iuA'));

&#x20;           const lsItem = studyItems.find(item => item.innerText.includes("Long/Short Ratio"));



&#x20;           if (lsItem) {

&#x20;               const valueEl = lsItem.querySelector('.valueValue-l31H9iuA');

&#x20;               results.push({

&#x20;                   chartIndex: i + 1,

&#x20;                   symbol: frameDoc.querySelector('.item-l31H9iuA:not(.study-l31H9iuA)')?.innerText.split('\\n')\[0] || "Unknown",

&#x20;                   fullText: lsItem.innerText,

&#x20;                   valueHtml: valueEl ? valueEl.outerHTML : null,

&#x20;                   isPureLeaf: valueEl ? valueEl.children.length === 0 : null

&#x20;               });

&#x20;           }

&#x20;       } catch (e) { console.error(`Chart ${i+1}: Access denied.`); }

&#x20;   }

&#x20;   console.table(results);

})();



DOM Analysis Summary

Full innerText (Example from Chart 1 - BTC): "<CoinGlass> Long/Short Ratio (Accounts)\\nNo Filter\\n1.5130"

Outer HTML of numeric value element: The value is held in a div with the title "value". Example

<div class="valueValue-l31H9iuA apply-common-tooltip" title="value" style="color: rgb(34, 171, 148);">1.5130</div>

Leaf Node Confirmation: Confirmed. The element holding the ratio is a pure leaf node (containing only the numeric text).



\------------------------



The analysis of the Aggregated Open Interest indicator for all 9 charts in your grid is complete.



JavaScript Extraction Snippet

You can run this in your console to fetch the Open Interest values for all 9 charts:

js

(async function() {

&#x20;   const iframes = Array.from(document.querySelectorAll('iframe'));

&#x20;   const results = \[];

&#x20;   

&#x20;   for (let i = 0; i < iframes.length; i++) {

&#x20;       try {

&#x20;           const frameDoc = iframes\[i].contentDocument || iframes\[i].contentWindow.document;

&#x20;           const studyItems = Array.from(frameDoc.querySelectorAll('.item-l31H9iuA.study-l31H9iuA'));

&#x20;           const oiItem = studyItems.find(item => item.innerText.includes("Aggregated Open Interest"));



&#x20;           if (oiItem) {

&#x20;               const valueElements = Array.from(oiItem.querySelectorAll('.valueValue-l31H9iuA'));

&#x20;               results.push({

&#x20;                   chartIndex: i + 1,

&#x20;                   symbol: frameDoc.querySelector('.item-l31H9iuA:not(.study-l31H9iuA)')?.innerText.split('\\n')\[0] || "Unknown",

&#x20;                   fullText: oiItem.innerText,

&#x20;                   values: valueElements.map(el => ({

&#x20;                       html: el.outerHTML,

&#x20;                       isPureLeaf: el.children.length === 0,

&#x20;                       text: el.innerText

&#x20;                   }))

&#x20;               });

&#x20;           }

&#x20;       } catch (e) { console.error(`Chart ${i+1}: Access denied.`); }

&#x20;   }

&#x20;   console.log(results);

})();

DOM Analysis Summary

Full innerText (Example from Chart 1 - BTC): "<CoinGlass> Aggregated Open Interest(STABLECOIN-margined,Candles)\\nopen No Filter\\n343.79K\\n344.634K\\n343.731K\\n344.47K" (Note: This indicator provides four values, likely representing the OHLC of the Open Interest.)

Outer HTML of numeric value elements: Each value is held in a div with the class .valueValue-l31H9iuA. Example of the current value:

<div class="valueValue-l31H9iuA apply-common-tooltip" title="<CoinGlass> Aggregated Open Interest(STABLECOIN-margined,Candles) (, open, No Filter, , )" style="color: rgb(34, 171, 148);">344.47K</div>

Leaf Node Confirmation: Confirmed. All four elements holding the Open Interest numeric values are pure leaf nodes (containing only text).





\------------------



The analysis of the Whale Index indicator for all 9 charts in your grid is complete.



JavaScript Extraction Snippet

You can run this in your console to fetch the Whale Index values for all 9 charts:

js

(async function() {

&#x20;   const iframes = Array.from(document.querySelectorAll('iframe'));

&#x20;   const results = \[];

&#x20;   

&#x20;   for (let i = 0; i < iframes.length; i++) {

&#x20;       try {

&#x20;           const frameDoc = iframes\[i].contentDocument || iframes\[i].contentWindow.document;

&#x20;           const studyItems = Array.from(frameDoc.querySelectorAll('.item-l31H9iuA.study-l31H9iuA'));

&#x20;           const whaleItem = studyItems.find(item => item.innerText.includes("Whale Index"));



&#x20;           if (whaleItem) {

&#x20;               const valueEl = whaleItem.querySelector('.valueValue-l31H9iuA');

&#x20;               results.push({

&#x20;                   chartIndex: i + 1,

&#x20;                   symbol: frameDoc.querySelector('.item-l31H9iuA:not(.study-l31H9iuA)')?.innerText.split('\\n')\[0] || "Unknown",

&#x20;                   fullText: whaleItem.innerText,

&#x20;                   valueHtml: valueEl ? valueEl.outerHTML : null,

&#x20;                   isPureLeaf: valueEl ? valueEl.children.length === 0 : null

&#x20;               });

&#x20;           }

&#x20;       } catch (e) { console.error(`Chart ${i+1}: Access denied.`); }

&#x20;   }

&#x20;   console.table(results);

})();

DOM Analysis Summary

Full innerText (Example from Chart 1 - BTC): "<CoinGlass> Whale Index\\nNo Filter\\n−9.0200"

Outer HTML of numeric value element: The value is held in a div with the title "value". Example:

&#x20;   <div class="valueValue-l31H9iuA apply-common-tooltip" title="value" style="color: rgb(242, 54, 69);">−9.0200</div>

&#x20;   ```

3\.  \*\*Leaf Node Confirmation:\*\*  

&#x20;   \*\*Confirmed.\*\* The element holding the index is a pure leaf node (containing only the numeric text).





\-----------------------





The analysis of the Taker Buy/Sell Count indicator for all 9 charts in your grid is complete.



JavaScript Extraction Snippet

You can run this in your console to fetch the Taker Buy, Sell, and Delta values for all 9 charts:

js

(async function() {

&#x20;   const iframes = Array.from(document.querySelectorAll('iframe'));

&#x20;   const results = \[];

&#x20;   

&#x20;   for (let i = 0; i < iframes.length; i++) {

&#x20;       try {

&#x20;           const frameDoc = iframes\[i].contentDocument || iframes\[i].contentWindow.document;

&#x20;           const studyItems = Array.from(frameDoc.querySelectorAll('.item-l31H9iuA.study-l31H9iuA'));

&#x20;           const takerItem = studyItems.find(item => item.innerText.includes("Taker Buy/Sell Count"));



&#x20;           if (takerItem) {

&#x20;               const valueElements = Array.from(takerItem.querySelectorAll('.valueValue-l31H9iuA'));

&#x20;               results.push({

&#x20;                   chartIndex: i + 1,

&#x20;                   symbol: frameDoc.querySelector('.item-l31H9iuA:not(.study-l31H9iuA)')?.innerText.split('\\n')\[0] || "Unknown",

&#x20;                   fullText: takerItem.innerText,

&#x20;                   buy: {

&#x20;                       html: valueElements\[0]?.outerHTML,

&#x20;                       isLeaf: valueElements\[0]?.children.length === 0,

&#x20;                       text: valueElements\[0]?.innerText

&#x20;                   },

&#x20;                   sell: {

&#x20;                       html: valueElements\[1]?.outerHTML,

&#x20;                       isLeaf: valueElements\[1]?.children.length === 0,

&#x20;                       text: valueElements\[1]?.innerText

&#x20;                   },

&#x20;                   delta: {

&#x20;                       html: valueElements\[2]?.outerHTML,

&#x20;                       isLeaf: valueElements\[2]?.children.length === 0,

&#x20;                       text: valueElements\[2]?.innerText

&#x20;                   }

&#x20;               });

&#x20;           }

&#x20;       } catch (e) { console.error(`Chart ${i+1}: Access denied.`); }

&#x20;   }

&#x20;   console.table(results);

})();



DOM Analysis Summary

Full innerText (Example from Chart 1 - BTC): "<CoinGlass> Taker Buy/Sell Count\\nNo Filter\\n11.787K\\n−12.97K\\n−1.183K"

Outer HTML of numeric value elements: The indicator provides three values: Buy (Long), Sell (Short), and Delta. Example (Delta):

<div class="valueValue-l31H9iuA apply-common-tooltip" title="Delta" style="color: rgb(224, 41, 74);">−1.183K</div>



Leaf Node Confirmation: Confirmed. All three value elements (Buy, Sell, and Delta) are pure leaf nodes (containing only text). \*\*



\--------------------



The analysis of the Aggregated Futures Bid \& Ask (Coins Bid) indicator for all 9 charts in your grid is complete.



JavaScript Extraction Snippet

You can run this in your console to fetch the Bid and Ask (Coins) values for all 9 charts:



js

(async function() {

&#x20;   const iframes = Array.from(document.querySelectorAll('iframe'));

&#x20;   const results = \[];

&#x20;   

&#x20;   for (let i = 0; i < iframes.length; i++) {

&#x20;       try {

&#x20;           const frameDoc = iframes\[i].contentDocument || iframes\[i].contentWindow.document;

&#x20;           const studyItems = Array.from(frameDoc.querySelectorAll('.item-l31H9iuA.study-l31H9iuA'));

&#x20;           

&#x20;           // Find the item with BOTH "Aggregated Futures Bid \& Ask" and "Coins Bid"

&#x20;           const bidAskItem = studyItems.find(item => 

&#x20;               item.innerText.includes("Aggregated Futures Bid \& Ask") \&\& 

&#x20;               item.innerText.includes("Coins Bid")

&#x20;           );



&#x20;           if (bidAskItem) {

&#x20;               const valueElements = Array.from(bidAskItem.querySelectorAll('.valueValue-l31H9iuA'));

&#x20;               results.push({

&#x20;                   chartIndex: i + 1,

&#x20;                   symbol: frameDoc.querySelector('.item-l31H9iuA:not(.study-l31H9iuA)')?.innerText.split('\\n')\[0] || "Unknown",

&#x20;                   fullText: bidAskItem.innerText,

&#x20;                   bid: {

&#x20;                       html: valueElements\[0]?.outerHTML,

&#x20;                       isLeaf: valueElements\[0]?.children.length === 0,

&#x20;                       text: valueElements\[0]?.innerText

&#x20;                   },

&#x20;                   ask: {

&#x20;                       html: valueElements\[1]?.outerHTML,

&#x20;                       isLeaf: valueElements\[1]?.children.length === 0,

&#x20;                       text: valueElements\[1]?.innerText

&#x20;                   }

&#x20;               });

&#x20;           }

&#x20;       } catch (e) { console.error(`Chart ${i+1}: Access denied.`); }

&#x20;   }

&#x20;   console.table(results);

})();





Use code snippets with caution



DOM Analysis Summary

Full innerText (Example from Chart 1 - BTC): "<CoinGlass> Aggregated Futures Bid \& Ask\\n1 Main chart symbol Coins Bid No Filter\\n7.304K\\n−7.795K"

Outer HTML of numeric value elements: The indicator provides two values: Bid (Positive) and Ask (Negative). Example (Ask):



<div class="valueValue-l31H9iuA apply-common-tooltip" title="Aks" style="color: rgb(224, 41, 74);">−7.795K</div>



(Note: The title attribute in the DOM is misspelled as "Aks".)

Leaf Node Confirmation: Confirmed. Both the Bid and Ask value elements are pure leaf nodes (containing only text). \*\*



\-----------------





The analysis of the Aggregated Futures Bid \& Ask (Dollars Bid) indicator for all 9 charts in your grid is complete.



JavaScript Extraction Snippet

You can run this in your console to fetch the Bid and Ask (Dollars) values for all 9 charts:

js

(async function() {

&#x20;   const iframes = Array.from(document.querySelectorAll('iframe'));

&#x20;   const results = \[];

&#x20;   

&#x20;   for (let i = 0; i < iframes.length; i++) {

&#x20;       try {

&#x20;           const frameDoc = iframes\[i].contentDocument || iframes\[i].contentWindow.document;

&#x20;           const studyItems = Array.from(frameDoc.querySelectorAll('.item-l31H9iuA.study-l31H9iuA'));

&#x20;           

&#x20;           // Find the item with BOTH "Aggregated Futures Bid \& Ask" and "Dollars Bid"

&#x20;           const bidAskItem = studyItems.find(item => 

&#x20;               item.innerText.includes("Aggregated Futures Bid \& Ask") \&\& 

&#x20;               item.innerText.includes("Dollars Bid")

&#x20;           );



&#x20;           if (bidAskItem) {

&#x20;               const valueElements = Array.from(bidAskItem.querySelectorAll('.valueValue-l31H9iuA'));

&#x20;               results.push({

&#x20;                   chartIndex: i + 1,

&#x20;                   symbol: frameDoc.querySelector('.item-l31H9iuA:not(.study-l31H9iuA)')?.innerText.split('\\n')\[0] || "Unknown",

&#x20;                   fullText: bidAskItem.innerText,

&#x20;                   bid: {

&#x20;                       html: valueElements\[0]?.outerHTML,

&#x20;                       isLeaf: valueElements\[0]?.children.length === 0,

&#x20;                       text: valueElements\[0]?.innerText

&#x20;                   },

&#x20;                   ask: {

&#x20;                       html: valueElements\[1]?.outerHTML,

&#x20;                       isLeaf: valueElements\[1]?.children.length === 0,

&#x20;                       text: valueElements\[1]?.innerText

&#x20;                   }

&#x20;               });

&#x20;           }

&#x20;       } catch (e) { console.error(`Chart ${i+1}: Access denied.`); }

&#x20;   }

&#x20;   console.table(results);

})();



DOM Analysis Summary

Full innerText (Example from Chart 1 - BTC): "<CoinGlass> Aggregated Futures Bid \& Ask\\n1 Main chart symbol Dollars Bid No Filter\\n467.35M\\n−502.803M"

Outer HTML of numeric value elements: The indicator provides two values in Dollars: Bid (Positive) and Ask (Negative). Example (Bid):

<div class="valueValue-l31H9iuA apply-common-tooltip" title="Bid" style="color: rgb(46, 189, 176);">467.35M</div>

Leaf Node Confirmation: Confirmed. Both the Bid and Ask value elements are pure leaf nodes (containing only text). \*\*





\------------------





The analysis of the ATR 14 and ATR 100 indicators for all 9 charts in your grid is complete.



JavaScript Extraction Snippet

You can run this in your console to fetch the ATR values for all 9 charts:

js

(async function() {

&#x20;   const iframes = Array.from(document.querySelectorAll('iframe'));

&#x20;   const allResults = \[];

&#x20;   

&#x20;   for (let i = 0; i < iframes.length; i++) {

&#x20;       try {

&#x20;           const frameDoc = iframes\[i].contentDocument || iframes\[i].contentWindow.document;

&#x20;           const chartData = {

&#x20;               chartIndex: i + 1,

&#x20;               symbol: frameDoc.querySelector('.item-l31H9iuA:not(.study-l31H9iuA)')?.innerText.split('\\n')\[0] || "Unknown",

&#x20;               atr14: null,

&#x20;               atr100: null

&#x20;           };



&#x20;           const studyItems = Array.from(frameDoc.querySelectorAll('.item-l31H9iuA.study-l31H9iuA'));

&#x20;           

&#x20;           studyItems.forEach(item => {

&#x20;               const text = item.innerText;

&#x20;               if (text.includes("ATR")) {

&#x20;                   const valueEl = item.querySelector('.valueValue-l31H9iuA');

&#x20;                   const data = {

&#x20;                       fullText: text,

&#x20;                       valueHtml: valueEl ? valueEl.outerHTML : null,

&#x20;                       isPureLeaf: valueEl ? valueEl.children.length === 0 : null

&#x20;                   };



&#x20;                   if (text.includes("14")) chartData.atr14 = data;

&#x20;                   else if (text.includes("100")) chartData.atr100 = data;

&#x20;               }

&#x20;           });

&#x20;           allResults.push(chartData);

&#x20;       } catch (e) {

&#x20;           allResults.push({ chartIndex: i + 1, error: "Access denied" });

&#x20;       }

&#x20;   }

&#x20;   console.table(allResults);

})();



DOM Analysis Summary

Full innerText (Example from BTC):

ATR 14: "ATR\\n14\\n209.3"

ATR 100: "ATR\\n100\\n189.8"

Outer HTML of numeric value elements: The values are held in a div with the title "Plot". Example

<div class="valueValue-l31H9iuA apply-common-tooltip" title="Plot" style="color: rgb(128, 25, 34);">209.3</div>

Code



3\.  \*\*Leaf Node Confirmation:\*\*  

&#x20;   \*\*Confirmed.\*\* Both the ATR 14 and ATR 100 value elements are pure leaf nodes (containing only text)







