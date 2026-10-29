/* Luxe EZVIZ camera card · v1.0.36 · optional per-device uploaded image · idle UI unified with camera wall; retain v1.0.31 navigation recovery. */
(() => {
  'use strict';
  if (customElements.get('luxe-ezviz-card')) return;
  const FRAME_PATH = '/luxe_ezviz/static/player.html?v=1.1.0-audio-exclusive';

  // One same-origin coordinator owns sound/talk exclusivity for all Luxe EZVIZ
  // cards in this HA page. Muting is invoked directly inside each same-origin
  // player iframe so the newly selected sound can still start in the click task.
  const AUDIO_COORDINATOR = window.__luxeEzvizAudioCoordinator ||
    (window.__luxeEzvizAudioCoordinator = {
      cards:new Set(), owner:null, talkOwner:null,
      register(card){this.cards.add(card);},
      unregister(card){this.cards.delete(card);this.release(card);},
      cardForFrame(frame){return [...this.cards].find(card=>card._iframe===frame)||null;},
      releaseTalk(card){if(this.talkOwner===card)this.talkOwner=null;},
      release(card){
        if(this.owner===card)this.owner=null;
        if(this.talkOwner===card)this.talkOwner=null;
      },
      claim(card,mode='sound'){
        if(!this.cards.has(card))this.cards.add(card);
        if(this.talkOwner && this.talkOwner!==card)
          return {allowed:false,reason:'talk_in_progress',completion:Promise.resolve(false)};
        if(this.talkOwner===card && mode!=='talk')
          return {allowed:false,reason:'talk_in_progress',completion:Promise.resolve(false)};
        card._audioForceMuted=false;
        this.owner=card;
        if(mode==='talk')this.talkOwner=card;
        const tasks=[...this.cards].filter(other=>other!==card).map(other=>{
          try{return Promise.resolve(other._muteForAudioExclusivity());}
          catch(_){return Promise.resolve(false);}
        });
        const completion=Promise.all(tasks).then(results=>{
          if(this.owner!==card || (mode==='talk'&&this.talkOwner!==card))return false;
          if(results.some(ok=>ok!==true)){
            if(mode==='talk'&&this.talkOwner===card)this.talkOwner=null;
            return false;
          }
          return true;
        }).catch(()=>{
          if(mode==='talk'&&this.talkOwner===card)this.talkOwner=null;
          return false;
        });
        return {allowed:true,reason:null,completion};
      },
      claimFrame(frame,mode='sound'){
        const card=this.cardForFrame(frame);
        return card?this.claim(card,mode):{allowed:true,reason:null,completion:Promise.resolve(true)};
      }
    });

  const ICON_PLAY = '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M12.1 6.7 C10.2 5.6 9.3 6.9 9.3 9.2 L9.3 22.8 C9.3 25.1 10.2 26.4 12.1 25.3 L25.1 18 C27.7 16.5 27.7 15.5 25.1 14 Z"/></svg>';
  const HTML = `
    <style>
      :host{display:block;width:100%;min-width:0;color:#e9edf2;box-sizing:border-box}
      .card{position:relative;overflow:hidden;isolation:isolate;border:0;border-radius:14px;
        background:#03070a;box-shadow:none}
      .viewport{position:relative;aspect-ratio:16/9;min-width:0;overflow:hidden;
        background:#03070a}
      .frame-slot,iframe{position:absolute;inset:0;width:100%;height:100%;border:0}
      iframe{display:block;background:#03070a}
      /* Cover only the card's view while PiP is active. The iframe/player stays
         alive underneath, so its canvasCaptureStream continues feeding PiP. */
      .pip-placeholder{position:absolute;inset:0;z-index:2;display:flex;flex-direction:column;
        align-items:center;justify-content:center;gap:8px;padding:18px;text-align:center;
        background:radial-gradient(ellipse at 50% 42%,#172536 0%,#080e16 72%,#03070a 100%);
        color:#e5edf6;pointer-events:none;user-select:none}
      .pip-placeholder[hidden]{display:none!important}
      .pip-placeholder-icon{width:42px;height:42px;display:flex;align-items:center;justify-content:center;
        border:1px solid rgba(205,221,240,.22);border-radius:50%;
        background:rgba(210,225,244,.07);color:#d5e2f2}
      .pip-placeholder-icon svg{width:22px;height:22px;display:block;fill:none;stroke:currentColor;
        stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}
      .pip-placeholder-title{font-size:14px;line-height:1.4;font-weight:500;letter-spacing:.02em}
      .pip-placeholder-subtitle{font-size:11px;line-height:1.5;color:#91a1b5}
      /* Fullscreen the existing iframe; don't reconstruct the player. */
      iframe:fullscreen,iframe:-webkit-full-screen{position:fixed!important;inset:0!important;
        width:100vw!important;height:100vh!important;height:100dvh!important;
        max-width:none!important;max-height:none!important;background:#03070a}
      .overlay{position:absolute;inset:0;z-index:3;display:flex;flex-direction:column;
        align-items:center;justify-content:center;gap:10px;text-align:center;
        padding:16px;pointer-events:none}
      .overlay[hidden]{display:none!important}
      /* Match luxe-camera-wall: top-left product identity, unobstructed center play. */
      .camera-identity{position:absolute;top:10px;left:12px;max-width:calc(100% - 24px);
        box-sizing:border-box;display:flex;align-items:center;gap:8px;padding:7px 10px;
        border-radius:12px;background:rgba(10,14,20,.34);text-align:left;pointer-events:none}
      .camera-identity img{display:block;flex:0 0 40px;width:40px;height:42px;
        object-fit:contain}
      .camera-identity img[hidden]{display:none!important}
      .camera-identity-text{display:flex;flex-direction:column;gap:2px;min-width:0}
      .camera-room{font-size:15px;font-weight:600;color:#fff;line-height:1.22;white-space:nowrap}
      .camera-model{font-size:12px;font-weight:450;color:rgba(255,255,255,.58);
        line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .message[hidden]{display:none!important}
      .main-button{pointer-events:auto;appearance:none;display:inline-flex;align-items:center;justify-content:center;
        width:clamp(40px,5.5vw,54px);height:clamp(40px,5.5vw,54px);padding:0;border:0;border-radius:50%;
        background:rgba(255,255,255,.15);color:#fff;cursor:pointer;
        -webkit-tap-highlight-color:transparent;touch-action:manipulation;
        transition:background .16s ease,transform .16s ease}
      .main-button:hover{background:rgba(255,255,255,.25)}
      .main-button:active{transform:scale(.96)}
      .main-button:focus-visible{outline:2px solid #ccd9eb;outline-offset:3px}
      .main-button[hidden]{display:none}
      .main-button svg{width:24px;height:24px;display:block;fill:currentColor;stroke:none;margin-left:2px}
      .spinner{width:29px;height:29px;border-radius:50%;border:2px solid rgba(255,255,255,.22);
        border-top-color:#fff;animation:spin 1s linear infinite;display:none}
      .viewport[data-state="loading"] .spinner,.viewport[data-state="stopping"] .spinner{display:block}
      @keyframes spin{to{transform:rotate(360deg)}}
      .message{color:rgba(255,255,255,.77);font-size:12px;line-height:1.5;max-width:94%;
        overflow-wrap:anywhere;text-shadow:0 1px 2px rgba(0,0,0,.3)}
      .viewport[data-state="error"] .message{color:#eab8ad}
      @media(max-width:599px){.card{border-radius:12px}.main-button{width:clamp(40px,5.5vw,54px);height:clamp(40px,5.5vw,54px)}
        .camera-identity{top:8px;left:8px;max-width:calc(100% - 16px);
          gap:7px;padding:6px 8px;border-radius:10px}
        .camera-identity img{flex-basis:32px;width:32px;height:32px}
        .camera-room{font-size:14px}.camera-model{font-size:11px}}
      @media(prefers-reduced-motion:reduce){.spinner{animation-duration:1.8s}.main-button{transition:none}}
    </style>
    <div class="card">
      <div class="viewport" data-state="idle">
        <div class="frame-slot"></div>
        <div class="pip-placeholder" hidden aria-live="polite" aria-label="画中画播放中">
          <div class="pip-placeholder-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"></rect><path d="M13 12h6v5h-6z"></path></svg>
          </div>
          <div class="pip-placeholder-title">画中画播放中</div>
          <div class="pip-placeholder-subtitle">关闭悬浮窗口后自动恢复实时画面</div>
        </div>
        <div class="overlay" aria-live="polite">
          <div class="camera-identity" aria-label="萤石摄像机">
            <img alt="" draggable="false" hidden />
            <div class="camera-identity-text">
              <div class="camera-room">萤石摄像机</div>
              <div class="camera-model">设备信息加载中</div>
            </div>
          </div>
          <button type="button" class="main-button" aria-label="播放萤石摄像机">${ICON_PLAY}</button>
          <div class="spinner" aria-hidden="true"></div>
          <div class="message">点击播放</div>
        </div>
      </div>
    </div>`;
  const reasonText = (reason) => ({
    sdk_not_installed: '未安装 EZUIKit 9.0.5 本地 SDK',
    invalid_session: '播放授权参数无效',
    invalid_auth: '萤石授权已失效，请检查集成',
    cloud_unavailable: '萤石云连接失败，请稍后重试',
    encryption_unknown: '暂时无法确认设备加密状态，请检查后重试',
    device_serial_required: '未指定设备序列号，请填写 device_serial',
    invalid_device_serial: '设备序列号格式无效',
    device_serial_not_found: '未找到此序列号对应的萤石配置，请检查集成',
    camera_not_loaded: '设备配置尚未加载，请检查集成状态',
    invalid_configuration: '后端设备参数配置不正确',
    invalid_serial: '设备序列号不合法',
    device_not_found: '萤石云未找到该设备',
    invalid_channel: '设备不存在所选视频通道',
    device_permission: '当前应用无权访问该设备',
    invalid_request: '播放请求参数无效',
    timeout: '连接超时，请检查云端网络或套餐',
  }[reason] || `播放失败（${String(reason || 'unknown').replace(/[^A-Za-z0-9_.-]/g,'').slice(0,35)}）`);

  const extractErrorReason = err => {
    const known=['device_serial_required','invalid_device_serial','device_serial_not_found',
      'camera_not_loaded','invalid_configuration','encryption_unknown','invalid_auth',
      'cloud_unavailable','invalid_serial','device_not_found','invalid_channel',
      'device_permission','invalid_request'];
    for(const value of [err?.reason,err?.body?.reason,err?.data?.reason,
      err?.response?.reason,err?.response?.data?.reason]){
      if(typeof value==='string' && known.includes(value))return value;
    }
    const message=String(err?.message||'');
    for(const candidate of [message,err?.body,err?.response?.body]){
      if(typeof candidate!=='string')continue;
      try{const parsed=JSON.parse(candidate);if(known.includes(parsed?.reason))return parsed.reason;}catch(_){ }
      if(known.some(reason=>candidate.includes(reason))){
        return known.find(reason=>candidate.includes(reason));
      }
    }
    const status=Number(err?.status||err?.statusCode||err?.response?.status);
    if(status===404)return 'device_serial_not_found';
    if(status===401)return 'invalid_auth';
    return 'playback_error';
  };

  class LuxeEzvizCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({mode:'open'});
      this.shadowRoot.innerHTML = HTML;
      this._els = {
        viewport:this.shadowRoot.querySelector('.viewport'),
        overlay:this.shadowRoot.querySelector('.overlay'),
        btn:this.shadowRoot.querySelector('.main-button'),
        msg:this.shadowRoot.querySelector('.message'),
        slot:this.shadowRoot.querySelector('.frame-slot'),
        pipPlaceholder:this.shadowRoot.querySelector('.pip-placeholder'),
      };
      this._state='idle';this._iframe=null;this._session=null;this._id=null;this._stopReset=true;this._pipActive=false;this._isOffscreen=false;this._nativeFullscreenActive=false;
      this._frameStarted=false;this._audioForceMuted=false;this._audioSoundOn=false;
      this._timer=null;this._stopTimer=null;this._intersectionTimer=null;this._intersection=null;
      this._disconnectTimer=null;this._disconnectAt=0;this._disconnectGraceMs=1500;
      this._needsIdleAfterNavigation=false;
      this._navigationLeaving=false; // Suppress idle overlay only while the navigation is leaving.
      this._onMessage=this._onMessage.bind(this);
      this._onHidden=this._onHidden.bind(this);
      this._onNavigationRoute=this._onNavigationRoute.bind(this);
      this._els.btn.addEventListener('click',()=>this._begin());
    }
    setConfig(config) {
      if (!config || typeof config !== 'object') throw new Error('luxe-ezviz-card 配置错误');
      const serial = typeof config.device_serial === 'string' ? config.device_serial.trim().toUpperCase() : '';
      if(!/^[A-Z0-9_-]{4,64}$/.test(serial))throw new Error('luxe-ezviz-card 必须填写有效的 device_serial');
      this._config={
        device_serial:serial,
        title:typeof config.title==='string'?config.title.trim():'',
        room:typeof config.room==='string'?config.room.trim():'',
        model:typeof config.model==='string'?config.model.trim():'',
        image:typeof config.image==='string'?config.image.trim():'',
        muted:config.muted!==false,
      };
      this._metadata=null;
      this._metadataLastFetch=0;
      this._updateIdentity();
      this._setState(this._state);
      if(this.isConnected)this._loadMetadata();
    }
    _updateIdentity(){
      if(!this._config)return;
      const {room,model,image,title}=this._config;
      const data=this._metadata||{};
      const displayName=room||data.display_name||title||'萤石摄像机';
      const modelName=model||data.model||'萤石摄像机';
      const identity=this.shadowRoot.querySelector('.camera-identity');
      const photo=identity.querySelector('img');
      this.shadowRoot.querySelector('.camera-room').textContent=displayName;
      this.shadowRoot.querySelector('.camera-model').textContent=modelName;
      identity.setAttribute('aria-label',`${displayName} ${modelName}`);
      // Card-level override remains supported; otherwise use the per-device upload.
      // No uploaded image means the identity is text-only, without a reserved gap.
      const selectedImage=/^(?:\/local\/|https:\/\/)/.test(image) ? image
        : (typeof data.image_url==='string' && data.image_url.startsWith('/local/luxe-ezviz/images/') ? data.image_url : '');
      if(selectedImage){
        if(photo.getAttribute('src')!==selectedImage)photo.src=selectedImage;
        photo.hidden=false;
      }else{
        photo.hidden=true;
        photo.removeAttribute('src');
      }
      this._els.btn.setAttribute('aria-label',`播放${displayName}`);
    }
    async _loadMetadata(){
      if(!this._config||!this._hass?.callApi)return;
      const serial=this._config.device_serial;
      const now=Date.now();
      if(now-this._metadataLastFetch<2000)return;
      this._metadataLastFetch=now;
      try{
        const data=await this._hass.callApi('GET',`luxe_ezviz/metadata?device_serial=${encodeURIComponent(serial)}`);
        if(this._config?.device_serial!==serial||!data?.ok)return;
        this._metadata=data;
        this._updateIdentity();
      }catch(_){/* Metadata errors must not prevent playback. */}
    }
    set hass(value){this._hass=value;if(this.isConnected&&this._config)this._loadMetadata();}
    getCardSize(){return 4;}
    connectedCallback(){
      AUDIO_COORDINATOR.register(this);
      (window.__luxeEzvizNavigationInstances ||= new Set()).add(this);
      window.addEventListener('location-changed',this._onNavigationRoute);
      window.addEventListener('popstate',this._onNavigationRoute);
      clearTimeout(this._disconnectTimer);this._disconnectTimer=null;this._disconnectAt=0;
      window.addEventListener('message',this._onMessage);
      // This instance belongs to its current route; never assume a specific
      // dashboard slug. Reattachment may use a new route for the same card.
      this._attachedRoute=location.pathname.replace(/\/+$/,'')||'/';
      // If HA preserved the card during navigation, wait for STOP before
      // restoring idle. Reattachment must reveal the play overlay.
      {
        this._navigationLeaving=false;
        // A reattached HA Panel can preserve the hidden overlay DOM. Always sync it.
        if(this._needsIdleAfterNavigation && (this._iframe || this._state==='live' || this._state==='loading' || this._state==='stopping')){
          void this.stopForNavigation(false);
        }else{
          if(this._needsIdleAfterNavigation)this._needsIdleAfterNavigation=false;
          this._setState(this._state);
        }
      }
      this._loadMetadata();
      document.addEventListener('visibilitychange',this._onHidden);
      if ('IntersectionObserver' in window && !this._intersection) {
        this._intersection=new IntersectionObserver((entries)=>{
          this._isOffscreen=entries[0]?.intersectionRatio < 0.03;
          if (this._isOffscreen && (this._state==='live'||this._state==='loading') && !this._isFullscreen()) {
            clearTimeout(this._intersectionTimer);
            this._intersectionTimer=setTimeout(()=>{
              if(!this._pipActive&&!this._isFullscreen()){
                this._stop(true,'offscreen');
              }
            },1800);
          } else {
            clearTimeout(this._intersectionTimer);
          }
        },{threshold:[0,0.03]});
        this._intersection.observe(this);
      }
    }
    // Fullscreen iframe remains inside this card's shadow root. Some HA
    // layouts report an invisible host while the iframe is in the top layer;
    // don't mistake that for the user leaving the surveillance page.
    _isFullscreen(){
      if(this._nativeFullscreenActive)return true;
      const active=this.shadowRoot.fullscreenElement||document.fullscreenElement||document.webkitFullscreenElement;
      return Boolean(active && (active===this._iframe||active===this||
        active===this._els.viewport||this._els.viewport.contains(active)));
    }
    disconnectedCallback(){
      window.removeEventListener('location-changed',this._onNavigationRoute);
      window.removeEventListener('popstate',this._onNavigationRoute);
      // HA can briefly detach/reinsert a custom card while the browser enters
      // fullscreen. Removing the iframe immediately tears down the live cloud
      // session. Release listeners now, but defer session destruction until
      // this card is truly still detached after a short bounded grace period.
      window.removeEventListener('message',this._onMessage);
      document.removeEventListener('visibilitychange',this._onHidden);
      this._intersection?.disconnect();this._intersection=null;
      clearTimeout(this._intersectionTimer);this._intersectionTimer=null;
      clearTimeout(this._disconnectTimer);this._disconnectTimer=null;
      if(!this._iframe && !this._session && this._state!=='loading' && this._state!=='live'){
        window.__luxeEzvizNavigationInstances?.delete(this);
        AUDIO_COORDINATOR.unregister(this);return;
      }
      this._disconnectAt=Date.now();
      this._disconnectTimer=setTimeout(()=>{
        this._disconnectTimer=null;
        if(this.isConnected){
          // Defensive safeguard for any unusual lifecycle timing.
          return;
        }
        this._stop(true,'confirmed-detach');
      },this._disconnectGraceMs);
    }
    _onNavigationRoute(){
      const route=location.pathname.replace(/\/+$/,'')||'/';
      const activeRoute=this._attachedRoute||route;
      if(route!==activeRoute && (this._iframe || this._state==='live' || this._state==='loading' || this._state==='stopping')){
        void this.stopForNavigation();
      } else if(route===activeRoute){
        this._navigationLeaving=false;
        this._loadMetadata();
        if(this._needsIdleAfterNavigation && (this._iframe || this._state==='live' || this._state==='loading' || this._state==='stopping'))void this.stopForNavigation(false);
        else if(this._needsIdleAfterNavigation){this._needsIdleAfterNavigation=false;this._setState('idle');}
        else this._setState(this._state);
      }
    }
    _onHidden(){
      if(document.visibilityState==='hidden'&&!this._pipActive&&!this._isFullscreen()){this._stop(true,'hidden');
      }
    }
    _setPipVisual(active,via='unknown'){
      active=Boolean(active);
      const placeholder=this._els.pipPlaceholder;
      const shouldHide=!active;
      const changed=this._pipActive!==active||placeholder.hidden!==shouldHide;
      this._pipActive=active;
      placeholder.hidden=shouldHide;
      this._els.viewport.dataset.pip=active?'active':'inactive';
      if(changed){}
    }
    _setState(state,details='') {
      this._state=state;
      const {viewport,overlay,btn,msg}=this._els;
      viewport.dataset.state=state;
      overlay.hidden=state==='live'||this._navigationLeaving;
      btn.hidden=state==='loading'||state==='stopping';
      btn.disabled=state==='loading'||state==='stopping';
      btn.setAttribute('aria-label',state==='error'?'重新播放摄像机':`播放${this._config?.room||this._metadata?.display_name||this._config?.title||'萤石摄像机'}`);
      msg.textContent=details||({idle:'',loading:'正在连接视频…',error:'点击重试',stopping:'正在停止…'}[state]||'');
      msg.hidden=!msg.textContent;
    }
    async _begin(){
      if (this._state!=='idle'&&this._state!=='error')return;
      if (this._iframe) {this._els.msg.textContent='正在回收上一连接，请稍后重试';return;}
      if (!this._hass || !this._hass.callApi){this._setState('error','Home Assistant 尚未准备好');return;}
      this._setState('loading');
      this._frameStarted=false;this._audioForceMuted=false;this._audioSoundOn=false;
      const id=String(Date.now())+'-'+Math.random().toString(36).slice(2);
      this._id=id;
      try {
        const result=await this._hass.callApi('POST','luxe_ezviz/playback',{device_serial:this._config.device_serial});
        if (this._id!==id)return;
        if (!result?.ok||!result.accessToken||!result.url)throw new Error(result?.reason||'invalid_session');
        this._session={accessToken:result.accessToken,url:result.url,env:result.env};
        const frame=document.createElement('iframe');
        frame.title='EZVIZ encrypted video';
        frame.setAttribute('allow','autoplay; fullscreen; picture-in-picture; microphone');
        frame.setAttribute('allowfullscreen','');
        frame.setAttribute('referrerpolicy','no-referrer');
        // Prevent Safari briefly painting the iframe's initial about:blank white
        // document while the player HTML is loading. Keep the parent viewport dark
        // and reveal the iframe only after its actual document has loaded.
        frame.style.backgroundColor='#03070a';
        frame.style.colorScheme='dark';
        frame.style.visibility='hidden';
        this._iframe=frame;
        frame.addEventListener('load',()=>{
          if(this._iframe!==frame)return;
          frame.style.visibility='visible';
        },{once:true});
        frame.src=FRAME_PATH;
        this._els.slot.replaceChildren(frame);
        this._timer=setTimeout(()=>{
          if(this._id===id&&this._state==='loading')this._fail('timeout');
        },35000);
      } catch(err) {
        if(this._id!==id)return;
        this._fail(extractErrorReason(err));
      }
    }
    _onMessage(e){
      if(e.origin!==location.origin||!this._iframe||e.source!==this._iframe.contentWindow)return;
      const data=e.data;
      if(!data||data.type!=='LUXE_EZVIZ_FRAME')return;
      if(data.state==='READY'){
        if(!this._session||this._state!=='loading')return;
        const session=this._session;this._session=null;
        const frame=this._iframe,id=this._id;
        const startPlayer=async()=>{
          let soundAllowed=true;
          if(this._config?.muted===false){
            const claim=AUDIO_COORDINATOR.claim(this,'sound');
            soundAllowed=claim.allowed&&await claim.completion;
          }
          if(this._id!==id||this._iframe!==frame||this._state!=='loading')return;
          const muted=this._config?.muted!==false||!soundAllowed||
            this._audioForceMuted||AUDIO_COORDINATOR.owner!==this;
          this._frameStarted=true;
          frame.contentWindow.postMessage({type:'LUXE_EZVIZ_PARENT',id,
            command:'START',session,muted},location.origin);
        };
        void startPlayer().catch(()=>{
          if(this._id===id)this._fail('audio_coordination_failed');
        });
        return;
      }
      if(data.id!==this._id)return;
      if(data.state==='AUDIO_STATE'){
        this._audioSoundOn=Boolean(data.soundOn);
        if(this._audioSoundOn&&AUDIO_COORDINATOR.owner!==this)
          void this._muteForAudioExclusivity();
        return;
      }
      if(data.state==='TALK_STATE'){
        if(data.talkActive!==true)AUDIO_COORDINATOR.releaseTalk(this);
        return;
      }
      if(data.state==='PTZ_RPC'){
        // Only messages from our live iframe with a matching playback id.
        void this._handlePtzRpc(data);
        return;
      }
      if(data.state==='FIRST_FRAME'){
        if(this._state!=='loading')return;
        clearTimeout(this._timer);this._setState('live');
      }else if(data.state==='PIP_ENTERED'){
        if(this._state==='live')this._setPipVisual(true,'frame-entered');
      }else if(data.state==='PIP_EXITED'){
        this._setPipVisual(false,'frame-exited');
        if((document.visibilityState==='hidden'||(this._isOffscreen&&!this._isFullscreen()))&&
          (this._state==='live'||this._state==='loading'))this._stop(true,'pip-exited-hidden-offscreen');
      }else if(data.state==='NATIVE_FULLSCREEN_ENTERED'){
        if(this._state==='live')this._nativeFullscreenActive=true;
      }else if(data.state==='NATIVE_FULLSCREEN_EXITED'){
        this._nativeFullscreenActive=false;
        if((document.visibilityState==='hidden'||this._isOffscreen)&&
          (this._state==='live'||this._state==='loading'))this._stop(true,'native-fullscreen-exit-hidden-offscreen');
      }else if(data.state==='STOP_REQUEST'){
        // The control buttons live inside the iframe so playback, quality, and talk controls share one bar.
        if(this._state==='live'||this._state==='loading')this._stop(true,'control-stop');
      }else if(data.state==='STOPPED'){
        this._finishStop(this._id,this._state==='error'?false:this._stopReset);
      }else if(data.state==='ERROR'){
        if(this._state==='loading'||this._state==='live')this._fail(data.reason);
      }
    }
    async _handlePtzRpc(data){
      const requestId=data.requestId;
      if(!Number.isSafeInteger(requestId)||requestId<1||!this._config?.device_serial)return;
      const action=data.action;
      if(!['capability','pulse','start','stop','heartbeat'].includes(action))return;
      if(action!=='stop'&&this._state!=='live')return;
      const serial=this._config.device_serial;
      const frame=this._iframe,id=this._id;
      if(!frame||!id||!this._hass?.callApi)return;
      let result;
      try{
        if(action==='capability'){
          result=await this._hass.callApi('GET',`luxe_ezviz/ptz/capability?device_serial=${encodeURIComponent(serial)}`);
        }else{
          const payload={device_serial:serial,action};
          if(action==='pulse'||action==='start')payload.direction=data.direction;
          result=await this._hass.callApi('POST','luxe_ezviz/ptz/control',payload);
        }
      }catch(_){result={ok:false,reason:'ptz_request_failed'};}
      if(this._iframe!==frame||this._id!==id)return;
      try{frame.contentWindow?.postMessage({type:'LUXE_EZVIZ_PARENT',id,
        command:'PTZ_RESULT',requestId,result},location.origin);}catch(_){}
    }
    async _muteForAudioExclusivity(){
      this._audioForceMuted=true;
      if(!this._iframe||!this._frameStarted)return true;
      const frame=this._iframe;
      try{
        const control=frame.contentWindow?.__luxeEzvizAudioControl;
        if(typeof control?.mute!=='function')return false;
        const result=await Promise.race([
          Promise.resolve(control.mute()),
          new Promise(resolve=>setTimeout(()=>resolve(false),2200))
        ]);
        if(result===true)this._audioSoundOn=false;
        return result===true;
      }catch(_){return false;}
    }
    _ptzEmergencyStop(){
      const serial=this._config?.device_serial;
      if(!serial||!this._hass?.callApi)return;
      // Best effort; the server-side PTZ watchdog also handles lost requests.
      void this._hass.callApi('POST','luxe_ezviz/ptz/control',
        {device_serial:serial,action:'stop'}).catch(()=>{});
    }
    _fail(reason){
      if(this._state!=='loading'&&this._state!=='live')return;
      const msg=reasonText(reason);
      this._stop(false,'playback-error');
      this._setState('error',msg);
    }
    // Public navigation hook. Wait for the iframe STOP acknowledgement and
    // actual iframe teardown before the next camera Panel is mounted.
    async stopForNavigation(suppressUI=true){
      if(suppressUI){this._navigationLeaving=true;this._setState(this._state);}
      this._needsIdleAfterNavigation=true;
      clearTimeout(this._disconnectTimer);this._disconnectTimer=null;
      if(!this._iframe){
        if(this._state==='loading'||this._state==='live')this._stop(true,'navigation');
        return;
      }
      this._stop(true,'navigation');
      const deadline=Date.now()+5500;
      while((this._iframe || this._state==='stopping') && Date.now()<deadline){
        await new Promise(resolve=>setTimeout(resolve,50));
      }
      // The existing STOP fallback owns iframe cleanup; don't duplicate it.
    }
    _stop(reset=true,reason='unspecified'){
      this._ptzEmergencyStop();
      clearTimeout(this._disconnectTimer);this._disconnectTimer=null;
      this._setPipVisual(false,'stop');
      if(this._state==='stopping'){if(reset)this._stopReset=true;return;}
      clearTimeout(this._timer);
      this._session=null;
      this._stopReset=reset;
      const frame=this._iframe;
      const sessionId=this._id;
      if(frame){
        this._setState('stopping');
        try{frame.contentWindow?.postMessage({type:'LUXE_EZVIZ_PARENT',id:sessionId,command:'STOP'},location.origin);}catch(_){}
        clearTimeout(this._stopTimer);
        this._stopTimer=setTimeout(()=>this._finishStop(sessionId,reset),5200);
      }else this._finishStop(sessionId,reset);
    }
    _finishStop(sessionId=this._id,reset=this._stopReset){
      if(sessionId!==this._id)return;
      clearTimeout(this._stopTimer);this._stopTimer=null;
      this._frameStarted=false;this._audioSoundOn=false;this._audioForceMuted=false;
      AUDIO_COORDINATOR.release(this);
      clearTimeout(this._timer);this._timer=null;
      this._iframe?.remove();this._iframe=null;this._session=null;this._id=null;
      this._setPipVisual(false,'stop-finished');this._nativeFullscreenActive=false;
      this._stopReset=true;
      if(!this.isConnected){
        window.__luxeEzvizNavigationInstances?.delete(this);
        AUDIO_COORDINATOR.unregister(this);
      }
      if(reset){
        this._needsIdleAfterNavigation=false;
        // STOP may finish after the user has already returned to this Panel.
        if(this.isConnected && (location.pathname.replace(/\/+$/,'')||'/')===this._attachedRoute)this._navigationLeaving=false;
        this._setState('idle');
      }
      else if(this._state!=='error')this._setState('error','播放中断，请点击重试');
    }
  }
  customElements.define('luxe-ezviz-card',LuxeEzvizCard);
  window.customCards=window.customCards||[];
  if(!window.customCards.some(c=>c.type==='luxe-ezviz-card'))window.customCards.push({type:'luxe-ezviz-card',name:'Luxe EZVIZ',description:'萤石云加密视频卡片'});
})();
