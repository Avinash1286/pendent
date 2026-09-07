/** Hardware-independent reference; integration with an RTOS and storage driver is still required. */
export type CaptureState='idle'|'recording'|'saving'|'muted'|'error';
export interface Hardware {setMicrophonePower(on:boolean):void; haptic(pattern:'start'|'stop'|'bookmark'|'error'):void;}
export interface Storage {canStart():boolean; begin():void; bookmark():void; commit():Promise<void>;}
export class CaptureController {
 state:CaptureState='idle'; private privacyOff=false; private batteryPermitsCapture=true;
 constructor(private hw:Hardware,private storage:Storage){hw.setMicrophonePower(false);}
 async pressRecord(){
  if(this.state==='saving')return;
  if(this.state==='recording'){await this.stop();return;}
  if(this.privacyOff||!this.batteryPermitsCapture||!this.storage.canStart()){this.hw.haptic('error');return;}
  try{this.storage.begin();this.hw.setMicrophonePower(true);this.state='recording';this.hw.haptic('start');}
  catch{this.hw.setMicrophonePower(false);this.state='error';this.hw.haptic('error');}
 }
 bookmark(){if(this.state==='recording'){this.storage.bookmark();this.hw.haptic('bookmark');}}
 async setPrivacy(off:boolean){this.privacyOff=off;if(off){this.hw.setMicrophonePower(false);if(this.state==='recording')await this.stop();else if(this.state!=='saving'&&this.state!=='error')this.state='muted';}else if(this.state==='muted')this.state='idle';}
 async batteryCritical(){this.batteryPermitsCapture=false;if(this.state==='recording')await this.stop();}
 batteryRecovered(){this.batteryPermitsCapture=true;}
 private async stop(){
  this.hw.setMicrophonePower(false);this.state='saving';
  try{await this.storage.commit();this.state=this.privacyOff?'muted':'idle';this.hw.haptic('stop');}
  catch{this.state='error';this.hw.haptic('error');}
 }
}
