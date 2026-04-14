/*
 * Frida trace script for proving Moonside app live-state reads.
 *
 * Targets recovered from local RE artifacts:
 * - PluginController.readCharacteristic / readNotifications
 * - PluginController.writeCharacteristicWithResponse / writeCharacteristicWithoutResponse
 * - ReactiveBleClient.readCharacteristic / setupNotification
 * - ReactiveBleClient.writeCharacteristicWithResponse / writeCharacteristicWithoutResponse
 * - CharNotificationHandler.subscribeToNotifications / handleNotificationValue
 * - DeviceConnectionHandler.handleDeviceConnectionUpdateResult
 * - App-side BleDeviceConnector.readA1DeviceBleInfo / updateDeviceInfo / connectionChecker
 *
 * Usage example:
 *   frida -U -f <package.name> -l moonside_state_trace.js
 * Then trigger lamp refresh + toggle on/off in the app and compare the logs.
 */

'use strict';

function safeString(value) {
  try {
    if (value === null || value === undefined) {
      return String(value);
    }
    return value.toString();
  } catch (error) {
    return `<toString failed: ${error}>`;
  }
}

function bytesToHex(bytes) {
  if (!bytes) {
    return '<null>';
  }

  const out = [];
  for (let i = 0; i < bytes.length; i += 1) {
    const value = bytes[i] & 0xff;
    out.push((value < 16 ? '0' : '') + value.toString(16));
  }
  return out.join(' ');
}

function bytesToAscii(bytes) {
  if (!bytes) {
    return '<null>';
  }

  let out = '';
  for (let i = 0; i < bytes.length; i += 1) {
    const value = bytes[i] & 0xff;
    out += value >= 32 && value <= 126 ? String.fromCharCode(value) : '.';
  }
  return out;
}

function logByteArray(prefix, bytes) {
  console.log(`${prefix} len=${bytes ? bytes.length : 'null'} hex=${bytesToHex(bytes)} ascii=${bytesToAscii(bytes)}`);
}

function installOverloadHook(overload, name, handlers) {
  overload.implementation = function () {
    const args = Array.prototype.slice.call(arguments);

    if (handlers && handlers.onEnter) {
      try {
        handlers.onEnter.call(this, args);
      } catch (error) {
        console.log(`[hook-error:${name}:enter] ${error}`);
      }
    } else {
      console.log(`[${name}] ${args.map(safeString).join(' | ')}`);
    }

    const result = overload.call(this, ...args);

    if (handlers && handlers.onLeave) {
      try {
        handlers.onLeave.call(this, result, args);
      } catch (error) {
        console.log(`[hook-error:${name}:leave] ${error}`);
      }
    }

    return result;
  };
}

function installMethodHooks(className, methodName, options) {
  try {
    const Klass = Java.use(className);
    const method = Klass[methodName];
    if (!method) {
      console.log(`[skip] ${className}.${methodName} not found`);
      return;
    }

    const overloads = method.overloads || [];
    overloads.forEach((overload, index) => {
      installOverloadHook(overload, `${className}.${methodName}#${index}`, options);
    });
    console.log(`[hooked] ${className}.${methodName} (${overloads.length} overloads)`);
  } catch (error) {
    console.log(`[skip] ${className}.${methodName}: ${error}`);
  }
}

function installHooks() {
  Java.perform(function () {
    console.log('[trace] Moonside state trace starting');

  installMethodHooks(
    'com.signify.hue.flutterreactiveble.PluginController',
    'readCharacteristic',
    {
      onEnter(args) {
        console.log('[plugin.readCharacteristic] MethodCall=' + safeString(args[0]));
      },
    }
  );

  installMethodHooks(
    'com.signify.hue.flutterreactiveble.PluginController',
    'readNotifications',
    {
      onEnter(args) {
        console.log('[plugin.readNotifications] MethodCall=' + safeString(args[0]));
      },
    }
  );

  installMethodHooks(
    'com.signify.hue.flutterreactiveble.PluginController',
    'writeCharacteristicWithResponse',
    {
      onEnter(args) {
        console.log('[plugin.writeWithResponse] MethodCall=' + safeString(args[0]));
      },
    }
  );

  installMethodHooks(
    'com.signify.hue.flutterreactiveble.PluginController',
    'writeCharacteristicWithoutResponse',
    {
      onEnter(args) {
        console.log('[plugin.writeWithoutResponse] MethodCall=' + safeString(args[0]));
      },
    }
  );

  installMethodHooks(
    'com.signify.hue.flutterreactiveble.ble.ReactiveBleClient',
    'readCharacteristic',
    {
      onEnter(args) {
        console.log(
          '[ble.readCharacteristic] device=' +
            safeString(args[0]) +
            ' uuid=' +
            safeString(args[1]) +
            ' instanceId=' +
            safeString(args[2])
        );
      },
    }
  );

  installMethodHooks(
    'com.signify.hue.flutterreactiveble.ble.ReactiveBleClient',
    'setupNotification',
    {
      onEnter(args) {
        console.log(
          '[ble.setupNotification] device=' +
            safeString(args[0]) +
            ' uuid=' +
            safeString(args[1]) +
            ' instanceId=' +
            safeString(args[2])
        );
      },
    }
  );

  installMethodHooks(
    'com.signify.hue.flutterreactiveble.ble.ReactiveBleClient',
    'writeCharacteristicWithResponse',
    {
      onEnter(args) {
        console.log(
          '[ble.writeWithResponse] device=' +
            safeString(args[0]) +
            ' uuid=' +
            safeString(args[1]) +
            ' instanceId=' +
            safeString(args[2])
        );
        logByteArray('[ble.writeWithResponse.bytes]', args[3]);
      },
    }
  );

  installMethodHooks(
    'com.signify.hue.flutterreactiveble.ble.ReactiveBleClient',
    'writeCharacteristicWithoutResponse',
    {
      onEnter(args) {
        console.log(
          '[ble.writeWithoutResponse] device=' +
            safeString(args[0]) +
            ' uuid=' +
            safeString(args[1]) +
            ' instanceId=' +
            safeString(args[2])
        );
        logByteArray('[ble.writeWithoutResponse.bytes]', args[3]);
      },
    }
  );

  installMethodHooks(
    'com.signify.hue.flutterreactiveble.channelhandlers.CharNotificationHandler',
    'subscribeToNotifications',
    {
      onEnter(args) {
        console.log('[notify.subscribe] request=' + safeString(args[0]));
      },
    }
  );

  installMethodHooks(
    'com.signify.hue.flutterreactiveble.channelhandlers.CharNotificationHandler',
    'handleNotificationValue',
    {
      onEnter(args) {
        console.log('[notify.value] characteristic=' + safeString(args[0]));
        logByteArray('[notify.value.bytes]', args[1]);
      },
    }
  );

  installMethodHooks(
    'com.signify.hue.flutterreactiveble.channelhandlers.DeviceConnectionHandler',
    'handleDeviceConnectionUpdateResult',
    {
      onEnter(args) {
        console.log('[connection.update] deviceInfo=' + safeString(args[0]));
      },
    }
  );

    Java.enumerateLoadedClasses({
      onMatch(name) {
        if (name.indexOf('BleDeviceConnector') === -1) {
          return;
        }

        installMethodHooks(name, 'readA1DeviceBleInfo', {
          onEnter(args) {
            console.log(`[app.readA1DeviceBleInfo] class=${name} argc=${args.length}`);
          },
        });

        installMethodHooks(name, 'updateDeviceInfo', {
          onEnter(args) {
            console.log(`[app.updateDeviceInfo] class=${name} argc=${args.length} args=${args.map(safeString).join(' | ')}`);
          },
        });

        installMethodHooks(name, 'connectionChecker', {
          onEnter(args) {
            console.log(`[app.connectionChecker] class=${name} argc=${args.length} args=${args.map(safeString).join(' | ')}`);
          },
        });
      },
      onComplete() {
        console.log('[trace] Moonside state trace hooks installed');
        console.log('[trace] Next action: capture refresh, then toggle ON and OFF while collecting write, read, and notify logs together');
      },
    });
  });
}

function waitForJava() {
  if (!Java.available) {
    console.log('[trace] Java not available yet; retrying...');
    setTimeout(waitForJava, 500);
    return;
  }

  try {
    installHooks();
  } catch (error) {
    console.log('[trace] Hook install failed, retrying: ' + error);
    setTimeout(waitForJava, 500);
  }
}

setImmediate(waitForJava);
