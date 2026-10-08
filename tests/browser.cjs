const assert=require('node:assert/strict'),fs=require('node:fs'),{chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true}),page=await browser.newPage({viewport:{width:1440,height:1080}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));let checks=0;const check=(a,b,l)=>{assert.deepEqual(a,b,l);checks++};
 try{
  await page.goto('http://127.0.0.1:5000');await page.getByRole('link',{name:'Organiser sign in',exact:true}).click();
  await page.getByLabel('Username').fill('organiser');await page.getByLabel('Password').fill('browser-test-password');await page.getByRole('button',{name:'Sign in ↗',exact:true}).click();
  await page.getByRole('link',{name:'＋ Create an event',exact:true}).click();await page.getByLabel('Event name',{exact:true}).fill('Garden workshop');
  const d=new Date();d.setDate(d.getDate()+5);await page.getByLabel('Date',{exact:true}).fill(d.toISOString().slice(0,10));await page.getByLabel('Start time').fill('09:30');
  await page.getByLabel('Venue').fill('Community hall');await page.getByLabel('Capacity',{exact:true}).fill('2');await page.getByLabel('Description').fill('A hands-on day in the garden.');await page.getByRole('button',{name:'Create event ↗',exact:true}).click();
  check(await page.getByRole('heading',{name:'Garden workshop',exact:true}).isVisible(),true,'Create');
  await page.getByLabel('Attendee name',{exact:true}).fill('Jane');await page.getByLabel('Email (optional)').fill('jane@example.com');await page.getByRole('button',{name:'Register attendee',exact:true}).click();
  await page.getByRole('button',{name:'Check in Jane',exact:true}).click();check(await page.getByRole('button',{name:'Undo check-in Jane',exact:true}).isVisible(),true,'Check-in');
  const promise=page.waitForEvent('download');await page.getByRole('link',{name:'Download attendees ↓',exact:true}).click();const dl=await promise;
  check(fs.readFileSync(await dl.path(),'utf8').includes('Jane,jane@example.com,Yes'),true,'CSV');
  await page.reload();check(await page.getByRole('button',{name:'Undo check-in Jane',exact:true}).isVisible(),true,'Persistence');
  await page.getByRole('link',{name:'Edit event',exact:true}).click();await page.getByLabel('Event name',{exact:true}).fill('Garden gathering');await page.getByRole('button',{name:'Save changes ↗',exact:true}).click();
  check(await page.getByRole('heading',{name:'Garden gathering',exact:true}).isVisible(),true,'Edit');
  fs.mkdirSync('test-results',{recursive:true});await page.screenshot({path:'test-results/event-details.png',fullPage:true});await page.getByRole('link',{name:'Event desk',exact:true}).click();await page.screenshot({path:'test-results/event-desktop.png',fullPage:true});
  for(const width of [320,390,768,1440]){await page.setViewportSize({width,height:1000});check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`Dashboard fits ${width}`);await page.getByRole('link',{name:'View occasion',exact:true}).click();check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`Detail fits ${width}`);if(width===390)await page.screenshot({path:'test-results/event-mobile.png',fullPage:true});await page.getByRole('link',{name:'Event desk',exact:true}).click();}
  await page.getByRole('link',{name:'View occasion',exact:true}).click();await page.getByRole('link',{name:'Delete event',exact:true}).click();await page.getByRole('link',{name:'Keep event',exact:true}).click();check(await page.getByRole('heading',{name:'Garden gathering',exact:true}).isVisible(),true,'Cancel delete');
  await page.getByRole('link',{name:'Delete event',exact:true}).click();await page.getByRole('button',{name:'Yes, delete event',exact:true}).click();check(await page.getByText('No events in this collection yet.',{exact:true}).isVisible(),true,'Delete');check(errors,[],'Browser errors');console.log(`PASS: ${checks} browser checks for login, event CRUD, guests, check-in, CSV, persistence and mobile.`);
 }catch(e){fs.mkdirSync('test-results',{recursive:true});await page.screenshot({path:'test-results/failure.png',fullPage:true});throw e}finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
